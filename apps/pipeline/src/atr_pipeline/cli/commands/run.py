"""CLI command: atr run — execute a pipeline stage range for a document."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import (
    finish_run,
    set_run_manifest_ref,
    start_run,
    update_run_provenance,
)
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.log_file import attach_run_log_handler, detach_run_log_handler
from atr_pipeline.runner.manifest_builder import build_run_manifest, git_head
from atr_pipeline.runner.plan import (
    SOURCE_ONLY_STAGES,
    WALKING_SKELETON_STAGES,
    resolve_stage_range,
)
from atr_pipeline.runner.registry import build_stage_registry
from atr_pipeline.runner.stage_context import StageContext, parse_page_filter
from atr_pipeline.runner.summary_builder import build_run_summary
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.store.atomic_write import atomic_write_text
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.source_manifest_v1 import SourceManifestV1

logger = logging.getLogger("atr_pipeline")


def run(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    from_stage: str = typer.Option("ingest", "--from", help="First stage to run"),
    to_stage: str = typer.Option("qa", "--to", help="Last stage to run"),
    edition: str = typer.Option("all", "--edition", help="Edition: 'en' (source-only) or 'all'"),
    pages: str = typer.Option("", "--pages", help="Page filter: '15' or '15,18-20'"),
    review_only: bool = typer.Option(
        False,
        "--review-only",
        help=(
            "Escape hatch for the PublishStage QA gate: build a clearly-marked "
            "DRAFT bundle over blocking QA findings (for human review) instead "
            "of refusing. Default is to refuse on blocking QA. Must be passed "
            "explicitly on the CLI — there is no env-var toggle (guards.md G1)."
        ),
    ),
) -> None:
    """Run a range of pipeline stages for a document."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)
    conn = open_registry(config.repo_root / "var" / "registry.db")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    cfg_hash = content_hash(config.model_dump(mode="json"))
    start_run(
        conn,
        run_id=run_id,
        document_id=doc,
        pipeline_version=config.pipeline.version,
        config_hash=cfg_hash,
        git_commit=git_head(),
        edition=edition,
    )

    log_handler = attach_run_log_handler(config.artifact_root, run_id)

    page_filter = parse_page_filter(pages) if pages else None

    stages = resolve_stage_range(from_stage=from_stage, to_stage=to_stage, edition=edition)
    registry = build_stage_registry()
    ctx = StageContext(
        run_id=run_id,
        document_id=doc,
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=config.repo_root,
        logger=logger,
        edition=edition,
        page_filter=page_filter,
        publish_review_only=review_only,
    )

    if review_only:
        typer.echo(
            "REVIEW-ONLY: PublishStage will build a DRAFT bundle over blocking QA "
            "if present — do not release it as-is."
        )
    if page_filter:
        typer.echo(f"Page filter: {sorted(page_filter)}")
    typer.echo(f"Running stages: {' → '.join(stages)}")
    has_errors = False
    qa_summary_ref: str | None = None
    # When ``--from`` skips upstream stages, seed ``upstream_refs`` with the
    # content hashes of the skipped stages' on-disk summary artifacts so the
    # first executed stage keys against real upstream content rather than an
    # empty (aliased) prefix (S5U-1227). With the content-bearing summaries
    # (page_refs), these hashes change whenever upstream per-page content
    # changes — exactly the integrity a full run would have threaded through.
    upstream_refs: list[str] = _seed_upstream_refs(
        store, document_id=doc, resolved_stages=stages, edition=edition
    )
    if upstream_refs:
        typer.echo(f"Seeded {len(upstream_refs)} upstream ref(s) from prior --from stages")

    for stage_name in stages:
        stage = registry[stage_name]
        typer.echo(f"  [{stage_name}]")

        result = execute_stage(stage, ctx, input_hashes=list(upstream_refs))

        if result.cached:
            typer.echo("    (cached)")
        if not result.success:
            typer.echo(f"    FAILED: {result.error}", err=True)
            has_errors = True
            break

        if result.artifact_ref is not None:
            upstream_refs.append(result.artifact_ref.content_hash)

        # Capture source PDF fingerprint after ingest for run provenance
        if stage_name == "ingest" and result.artifact_ref is not None:
            ingest_data = store.get_json(result.artifact_ref)
            manifest_v1 = SourceManifestV1.model_validate(ingest_data)
            update_run_provenance(
                conn, run_id=run_id, source_pdf_sha256=manifest_v1.source_pdf_sha256
            )

        if stage_name == "qa" and result.artifact_ref is not None:
            qa_summary_ref = result.artifact_ref.relative_path

    status = "failed" if has_errors else "completed"
    try:
        _finalize_run(
            conn,
            store=store,
            doc=doc,
            run_id=run_id,
            status=status,
            qa_summary_ref=qa_summary_ref,
            stages=stages,
            page_filter=page_filter,
            artifact_root=config.artifact_root,
        )
    finally:
        detach_run_log_handler(log_handler)
        conn.close()

    if has_errors:
        typer.echo(f"Run {run_id} finished with errors.")
        raise typer.Exit(1)
    typer.echo(f"Run {run_id} completed successfully.")


def _seed_upstream_refs(
    store: ArtifactStore,
    *,
    document_id: str,
    resolved_stages: list[str],
    edition: str,
) -> list[str]:
    """Resolve content hashes of the stages skipped by ``--from``.

    When a run starts mid-pipeline (``--from <stage>``), the stages before the
    first resolved stage are not executed, so ``upstream_refs`` would otherwise
    start empty — aliasing the downstream cache key across whatever upstream
    content happens to be on disk (S5U-1227). This seeds ``upstream_refs`` with
    the content hash of each skipped stage's latest on-disk summary artifact, in
    plan order, reproducing the prefix a full run would have accumulated by the
    time it reached the first resolved stage.

    The skipped set is the slice of the full edition plan that precedes
    ``resolved_stages[0]`` — derived from the full plan directly (not by
    re-resolving a range) so the prefix is unambiguous even when the resolved
    range is empty.

    The summary artifact is written by the executor at
    ``{doc}/{stage_name}/document/{doc}/{content_hash}.json``; the filename
    stem *is* the content hash. A skipped stage whose summary artifact is
    absent (never run) is omitted — there is no upstream content to key
    against, and the downstream stage will surface the missing-input error on
    its own rather than serve a silent stale hit.
    """
    if not resolved_stages:
        return []
    full_plan = SOURCE_ONLY_STAGES if edition == "en" else WALKING_SKELETON_STAGES
    first = resolved_stages[0]
    if first not in full_plan:
        return []
    skipped = full_plan[: full_plan.index(first)]
    seeded: list[str] = []
    for stage_name in skipped:
        latest = store.resolve_latest_path(
            document_id=document_id,
            schema_family=stage_name,
            scope="document",
            entity_id=document_id,
        )
        if latest is None:
            logger.warning(
                "--from seed: no summary artifact on disk for skipped stage %r; "
                "downstream cache key will omit it (re-run from an earlier stage "
                "if this is unexpected)",
                stage_name,
            )
            continue
        seeded.append(latest.stem)
    return seeded


def _finalize_run(  # noqa: PLR0913 — cohesive run-finalization plumbing
    conn: sqlite3.Connection,
    *,
    store: ArtifactStore,
    doc: str,
    run_id: str,
    status: str,
    qa_summary_ref: str | None,
    stages: list[str],
    page_filter: frozenset[str] | None,
    artifact_root: Path,
) -> None:
    """Finish the run, persist its manifest, and write the flat run summary."""
    finish_run(conn, run_id=run_id, status=status, qa_summary_ref=qa_summary_ref)

    manifest_ref = store.put_json(
        document_id=doc,
        schema_family="run_manifest.v1",
        scope="run",
        entity_id=run_id,
        data=build_run_manifest(conn, run_id=run_id),
    )
    set_run_manifest_ref(conn, run_id=run_id, ref=manifest_ref.relative_path)

    # Write flat run_summary.json at artifact root for LLM observability
    atomic_write_text(
        artifact_root / "run_summary.json",
        build_run_summary(
            conn,
            run_id=run_id,
            document_id=doc,
            stages_requested=stages,
            page_filter=page_filter,
        ).model_dump_json(indent=2)
        + "\n",
    )

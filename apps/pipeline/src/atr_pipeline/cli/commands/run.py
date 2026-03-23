"""CLI command: atr run — execute a pipeline stage range for a document."""

from __future__ import annotations

import logging
import uuid

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
from atr_pipeline.runner.plan import resolve_stage_range
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
    )

    if page_filter:
        typer.echo(f"Page filter: {sorted(page_filter)}")
    typer.echo(f"Running stages: {' → '.join(stages)}")
    has_errors = False
    qa_summary_ref: str | None = None

    for stage_name in stages:
        stage = registry[stage_name]
        typer.echo(f"  [{stage_name}]")

        result = execute_stage(stage, ctx)

        if result.cached:
            typer.echo("    (cached)")
        if not result.success:
            typer.echo(f"    FAILED: {result.error}", err=True)
            has_errors = True
            break

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
        finish_run(conn, run_id=run_id, status=status, qa_summary_ref=qa_summary_ref)

        manifest = build_run_manifest(conn, run_id=run_id)
        manifest_ref = store.put_json(
            document_id=doc,
            schema_family="run_manifest.v1",
            scope="run",
            entity_id=run_id,
            data=manifest,
        )
        set_run_manifest_ref(conn, run_id=run_id, ref=manifest_ref.relative_path)

        # Write flat run_summary.json at artifact root for LLM observability
        summary = build_run_summary(
            conn,
            run_id=run_id,
            document_id=doc,
            stages_requested=stages,
            page_filter=page_filter,
        )
        summary_json = summary.model_dump_json(indent=2) + "\n"
        atomic_write_text(config.artifact_root / "run_summary.json", summary_json)
    finally:
        detach_run_log_handler(log_handler)
        conn.close()

    if has_errors:
        typer.echo(f"Run {run_id} finished with errors.")
        raise typer.Exit(1)
    typer.echo(f"Run {run_id} completed successfully.")

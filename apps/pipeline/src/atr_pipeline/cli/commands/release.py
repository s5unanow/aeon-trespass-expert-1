"""CLI command: atr release — build a local release bundle."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import get_run, list_runs
from atr_pipeline.stages.publish.bundle_builder import (
    BundleRefs,
    build_release_bundle,
    flatten_raster_refs,
)
from atr_pipeline.stages.publish.qa_gate import QAGateError, evaluate_qa_gate
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.run_manifest_v1 import RunManifestV1

logger = logging.getLogger(__name__)


def _load_json_artifact(artifact_root: Path, ref: str) -> dict[str, object]:
    """Load a JSON artifact by ref path."""
    path = artifact_root / ref
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def release(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    output: str = typer.Option("", "--output", help="Output directory"),
    run_id: str = typer.Option("", "--run-id", help="Specific run to release (default: latest)"),
) -> None:
    """Build a local release bundle with render payloads and manifest."""
    config = load_document_config(doc)
    artifact_root = config.artifact_root
    output_dir = Path(output) if output else artifact_root / doc / "release"
    web_dist = config.repo_root / "apps" / "web" / "dist"

    run_data = _load_run(config.repo_root, doc, run_id=run_id or None)
    _check_qa_gate(artifact_root, run_data, block_on=set(config.qa.block_publish_on))
    refs = _extract_bundle_refs(artifact_root, run_data)

    manifest = build_release_bundle(
        document_id=doc,
        artifact_root=artifact_root,
        web_dist=web_dist if web_dist.exists() else None,
        output_dir=output_dir,
        pipeline_version=config.pipeline.version,
        refs=refs,
    )

    typer.echo(f"Release built: {output_dir}")
    typer.echo(f"  build_id: {manifest.build_id}")
    typer.echo(f"  run_id: {manifest.run_id}")
    typer.echo(f"  files: {len(manifest.files)}")


def _load_run(repo_root: Path, doc: str, *, run_id: str | None = None) -> dict[str, str | None]:
    """Load a run record by explicit id or fall back to the latest."""
    registry_path = repo_root / "var" / "registry.db"
    if not registry_path.exists():
        typer.echo("Error: no registry found. Run the pipeline first.", err=True)
        raise typer.Exit(1)

    conn = open_registry(registry_path)
    try:
        if run_id:
            row = get_run(conn, run_id)
            if row is None:
                typer.echo(f"Error: run {run_id} not found.", err=True)
                raise typer.Exit(1)
            if row["document_id"] != doc:
                typer.echo(
                    f"Error: run {run_id} belongs to document '{row['document_id']}', not '{doc}'.",
                    err=True,
                )
                raise typer.Exit(1)
            typer.echo(f"Using explicit run: {run_id}")
        else:
            runs = list_runs(conn, doc)
            if not runs:
                typer.echo("Error: no runs found for document.", err=True)
                raise typer.Exit(1)
            row = runs[0]
            typer.echo(f"Using latest run: {row['run_id']}")
        return {
            "run_id": row["run_id"],
            "qa_summary_ref": row["qa_summary_ref"],
            "run_manifest_ref": row["run_manifest_ref"],
        }
    finally:
        conn.close()


def _check_qa_gate(
    artifact_root: Path,
    run_data: dict[str, str | None],
    *,
    block_on: set[str],
) -> None:
    """Block release unless the run's QA gate allows it.

    Routes through the shared :func:`evaluate_qa_gate` so ``atr release`` agrees
    with ``PublishStage`` and ``make export`` on QA enforcement (S5U-893,
    follow-up to S5U-870). The fail-closed contract (`.claude/rules/guards.md`
    Rule G1) means a run with **no** resolvable QA summary refuses the release —
    not the legacy "warning, skip the gate" behaviour, which diverged from the
    two other paths. There is no ``--review-only`` escape hatch on ``atr
    release``: the legacy skip was a silent fail-open hole, not a workflow to
    preserve, so the gate always fails closed when no summary exists and always
    refuses on a blocking summary.
    """
    summary = _load_qa_summary(artifact_root, run_data)
    records = _load_qa_records(artifact_root, summary) if summary else []
    try:
        evaluate_qa_gate(
            context="Release",
            summary=summary,
            records=records,
            block_on=block_on,
            review_only=False,
            run_id=run_data.get("run_id") or "",
        )
    except QAGateError as exc:
        typer.echo(f"Release blocked: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo("QA gate passed.")


def _load_qa_summary(artifact_root: Path, run_data: dict[str, str | None]) -> QASummaryV1 | None:
    """Load the run's QA summary, or ``None`` when it cannot be resolved.

    Returns ``None`` when the run has no ``qa_summary_ref`` at all, or when the
    referenced artifact is missing/unreadable on disk (after logging). The
    shared gate treats ``None`` as a fail-closed refusal — never "pass by absent
    state".
    """
    qa_ref = run_data.get("qa_summary_ref")
    if not qa_ref:
        return None
    try:
        data = _load_json_artifact(artifact_root, qa_ref)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(
            "QA summary artifact %s for run %s is unreadable: %s",
            qa_ref,
            run_data.get("run_id"),
            exc,
        )
        return None
    return QASummaryV1.model_validate(data)


def _load_qa_records(artifact_root: Path, summary: QASummaryV1) -> list[QARecordV1]:
    """Load the QA records referenced by *summary* (for naming blocking codes).

    Missing/unreadable record artifacts are skipped with a warning — the gate
    still refuses on a blocking summary even when records cannot be named (it
    only degrades the refusal message, never the refusal itself).
    """
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = artifact_root / ref
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("QA record %s unreadable: %s", ref, exc)
            continue
        records.append(QARecordV1.model_validate(data))
    return records


def _extract_bundle_refs(artifact_root: Path, run_data: dict[str, str | None]) -> BundleRefs:
    """Build a BundleRefs from the run manifest in a single parse."""
    manifest_ref = run_data.get("run_manifest_ref")
    if not manifest_ref:
        typer.echo("Error: run has no manifest. Re-run the pipeline.", err=True)
        raise typer.Exit(1)

    data = _load_json_artifact(artifact_root, manifest_ref)
    manifest = RunManifestV1.model_validate(data)

    render_stage = next((s for s in manifest.stages if s.stage_name == "render"), None)
    if render_stage is None or not render_stage.artifact_ref:
        typer.echo("Error: no render stage in run manifest.", err=True)
        raise typer.Exit(1)

    render_data = _load_json_artifact(artifact_root, render_stage.artifact_ref)

    page_refs = render_data.get("page_refs")
    if not isinstance(page_refs, dict) or not page_refs:
        typer.echo("Error: render result has no page refs.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Using manifest refs for {len(page_refs)} render pages.")

    raw_image_refs = render_data.get("image_refs", {})

    flat_rasters = flatten_raster_refs(render_data.get("raster_refs", {}))

    return BundleRefs(
        render_pages={str(k): str(v) for k, v in page_refs.items()},
        companions={
            k: str(render_data[k])
            for k in ("glossary_ref", "search_docs_ref", "nav_ref")
            if render_data.get(k)
        },
        images=(
            {str(k): str(v) for k, v in raw_image_refs.items()}
            if isinstance(raw_image_refs, dict)
            else {}
        ),
        rasters=flat_rasters,
        run_id=run_data.get("run_id") or "",
        source_pdf_sha256=manifest.source_pdf_sha256,
    )

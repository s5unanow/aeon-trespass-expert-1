"""CLI command: atr release — build a local release bundle."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import get_run, list_runs
from atr_pipeline.stages.publish.bundle_builder import BundleRefs, build_release_bundle
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.run_manifest_v1 import RunManifestV1


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
    _check_qa_gate(artifact_root, run_data)
    render_refs, companion_refs, image_refs = _extract_artifact_refs(artifact_root, run_data)

    selected_run_id = run_data.get("run_id") or ""
    source_sha = _extract_source_sha(artifact_root, run_data)

    manifest = build_release_bundle(
        document_id=doc,
        artifact_root=artifact_root,
        web_dist=web_dist if web_dist.exists() else None,
        output_dir=output_dir,
        pipeline_version=config.pipeline.version,
        refs=BundleRefs(
            render_pages=render_refs,
            companions=companion_refs,
            images=image_refs,
            run_id=selected_run_id,
            source_pdf_sha256=source_sha,
        ),
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


def _check_qa_gate(artifact_root: Path, run_data: dict[str, str | None]) -> None:
    """Block release if the latest run has a blocking QA summary."""
    qa_ref = run_data.get("qa_summary_ref")
    if not qa_ref:
        typer.echo("Warning: latest run has no QA summary, skipping QA gate.", err=True)
        return

    data = _load_json_artifact(artifact_root, qa_ref)
    summary = QASummaryV1.model_validate(data)
    if summary.blocking:
        counts = summary.counts
        typer.echo(
            f"Release blocked: QA found blocking issues "
            f"(error={counts.error}, critical={counts.critical})",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo("QA gate passed.")


def _extract_source_sha(artifact_root: Path, run_data: dict[str, str | None]) -> str:
    """Extract source_pdf_sha256 from the run manifest's source_pdf_sha256 field."""
    manifest_ref = run_data.get("run_manifest_ref")
    if not manifest_ref:
        return ""
    data = _load_json_artifact(artifact_root, manifest_ref)
    manifest = RunManifestV1.model_validate(data)
    return manifest.source_pdf_sha256


def _extract_artifact_refs(
    artifact_root: Path, run_data: dict[str, str | None]
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Extract render page, companion, and image refs from the run manifest.

    Returns (render_page_refs, companion_refs, image_refs).
    Raises if no manifest or render stage is found.
    """
    manifest_ref = run_data.get("run_manifest_ref")
    if not manifest_ref:
        msg = "Latest run has no manifest. Re-run the pipeline."
        typer.echo(f"Error: {msg}", err=True)
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
    render_page_refs = {str(k): str(v) for k, v in page_refs.items()}

    companion_refs = {
        k: str(render_data[k])
        for k in ("glossary_ref", "search_docs_ref", "nav_ref")
        if render_data.get(k)
    }

    raw_image_refs = render_data.get("image_refs", {})
    image_refs = (
        {str(k): str(v) for k, v in raw_image_refs.items()}
        if isinstance(raw_image_refs, dict)
        else {}
    )

    return render_page_refs, companion_refs, image_refs

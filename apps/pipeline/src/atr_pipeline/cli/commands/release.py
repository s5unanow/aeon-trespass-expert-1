"""CLI command: atr release — build a local release bundle."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import list_runs
from atr_pipeline.stages.publish.bundle_builder import build_release_bundle
from atr_schemas.qa_summary_v1 import QASummaryV1


def _load_qa_summary(artifact_root: Path, ref: str) -> QASummaryV1:
    """Load a QASummaryV1 from an artifact ref path."""
    path = artifact_root / ref
    data = json.loads(path.read_text(encoding="utf-8"))
    return QASummaryV1.model_validate(data)


def release(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    output: str = typer.Option("", "--output", help="Output directory"),
) -> None:
    """Build a local release bundle with render payloads and manifest."""
    config = load_document_config(doc)
    artifact_root = config.artifact_root
    output_dir = Path(output) if output else artifact_root / doc / "release"
    web_dist = config.repo_root / "apps" / "web" / "dist"

    _check_qa_gate(config.repo_root, artifact_root, doc)

    manifest = build_release_bundle(
        document_id=doc,
        artifact_root=artifact_root,
        web_dist=web_dist if web_dist.exists() else None,
        output_dir=output_dir,
        pipeline_version=config.pipeline.version,
    )

    typer.echo(f"Release built: {output_dir}")
    typer.echo(f"  build_id: {manifest.build_id}")
    typer.echo(f"  files: {len(manifest.files)}")


def _check_qa_gate(repo_root: Path, artifact_root: Path, doc: str) -> None:
    """Block release if the latest run has a blocking QA summary."""
    registry_path = repo_root / "var" / "registry.db"
    if not registry_path.exists():
        typer.echo("Warning: no registry found, skipping QA gate.", err=True)
        return

    conn = open_registry(registry_path)
    try:
        runs = list_runs(conn, doc)
        if not runs:
            typer.echo("Warning: no runs found for document, skipping QA gate.", err=True)
            return

        latest = runs[0]
        qa_ref = latest["qa_summary_ref"]
        if not qa_ref:
            typer.echo("Warning: latest run has no QA summary, skipping QA gate.", err=True)
            return

        summary = _load_qa_summary(artifact_root, qa_ref)
        if summary.blocking:
            counts = summary.counts
            typer.echo(
                f"Release blocked: QA found blocking issues "
                f"(error={counts.error}, critical={counts.critical})",
                err=True,
            )
            raise typer.Exit(1)

        typer.echo("QA gate passed.")
    finally:
        conn.close()

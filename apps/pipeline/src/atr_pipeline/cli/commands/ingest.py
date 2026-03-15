"""CLI command: atr ingest — register and rasterize a source document."""

from __future__ import annotations

import uuid

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore


def ingest(
    doc: str = typer.Option(..., "--doc", help="Document id from configs/documents/"),
) -> None:
    """Ingest a source PDF: fingerprint, rasterize, and emit a manifest."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)
    conn = open_registry(config.repo_root / "var" / "registry.db")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_run(
        conn,
        run_id=run_id,
        document_id=doc,
        pipeline_version=config.pipeline.version,
        config_hash="",
    )

    ctx = StageContext(
        run_id=run_id,
        document_id=doc,
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=config.repo_root,
    )

    result = execute_stage(IngestStage(), ctx)

    if result.success:
        finish_run(conn, run_id=run_id, status="completed")
        typer.echo(f"Ingest completed. Artifact: {result.artifact_ref}")
    else:
        finish_run(conn, run_id=run_id, status="failed")
        typer.echo(f"Ingest failed: {result.error}", err=True)
        raise typer.Exit(1)

    conn.close()

"""CLI command: atr run — execute a pipeline stage range for a document."""

from __future__ import annotations

import logging
import uuid

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.plan import resolve_stage_range
from atr_pipeline.runner.registry import build_stage_registry
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.store.artifact_store import ArtifactStore

logger = logging.getLogger("atr_pipeline")


def run(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    from_stage: str = typer.Option("ingest", "--from", help="First stage to run"),
    to_stage: str = typer.Option("qa", "--to", help="Last stage to run"),
) -> None:
    """Run a range of pipeline stages for a document."""
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

    stages = resolve_stage_range(from_stage=from_stage, to_stage=to_stage)
    registry = build_stage_registry()
    ctx = StageContext(
        run_id=run_id,
        document_id=doc,
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=config.repo_root,
        logger=logger,
    )

    typer.echo(f"Running stages: {' → '.join(stages)}")
    has_errors = False

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

    status = "failed" if has_errors else "completed"
    finish_run(conn, run_id=run_id, status=status)
    conn.close()

    if has_errors:
        typer.echo(f"Run {run_id} finished with errors.")
        raise typer.Exit(1)
    typer.echo(f"Run {run_id} completed successfully.")

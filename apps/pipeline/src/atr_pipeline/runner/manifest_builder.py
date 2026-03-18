"""Build a RunManifestV1 from registry data after a pipeline run."""

from __future__ import annotations

import sqlite3
import subprocess

from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run
from atr_schemas.run_manifest_v1 import RunManifestV1, StageInvocationRef


def build_run_manifest(conn: sqlite3.Connection, *, run_id: str) -> RunManifestV1:
    """Assemble a RunManifestV1 from the runs table and stage_events."""
    run = get_run(conn, run_id)
    if run is None:
        msg = f"Run not found: {run_id}"
        raise ValueError(msg)

    events = list_stage_events(conn, run_id=run_id)
    stages = [
        StageInvocationRef(
            stage_name=ev["stage_name"],
            scope=ev["scope"],
            entity_id=ev["entity_id"],
            cache_key=ev["cache_key"],
            status=ev["status"],
            artifact_ref=ev["artifact_ref"] or "",
            duration_ms=ev["duration_ms"] or 0,
        )
        for ev in events
    ]

    return RunManifestV1(
        run_id=run_id,
        pipeline_version=run["pipeline_version"],
        git_commit=_git_head(),
        config_hash=run["config_hash"],
        started_at=run["started_at"],
        finished_at=run["finished_at"] or "",
        stages=stages,
        qa_summary_ref=run["qa_summary_ref"] or "",
    )


def _git_head() -> str:
    """Return the current HEAD commit SHA, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

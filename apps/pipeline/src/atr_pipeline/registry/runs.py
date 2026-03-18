"""Run lifecycle operations on the registry."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast


def start_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    document_id: str,
    pipeline_version: str,
    config_hash: str,
) -> None:
    """Record a new run start."""
    conn.execute(
        "INSERT INTO runs (run_id, document_id, pipeline_version, config_hash, started_at, status)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, document_id, pipeline_version, config_hash, _now_iso(), "running"),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str = "completed",
    qa_summary_ref: str | None = None,
    run_manifest_ref: str | None = None,
) -> None:
    """Mark a run as finished."""
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, qa_summary_ref = ?,"
        " run_manifest_ref = ? WHERE run_id = ?",
        (_now_iso(), status, qa_summary_ref, run_manifest_ref, run_id),
    )
    conn.commit()


def set_run_manifest_ref(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ref: str,
) -> None:
    """Store the run manifest artifact ref on a finished run."""
    conn.execute(
        "UPDATE runs SET run_manifest_ref = ? WHERE run_id = ?",
        (ref, run_id),
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    """Fetch a run by id."""
    cursor = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    return cast("sqlite3.Row | None", cursor.fetchone())


def list_runs(conn: sqlite3.Connection, document_id: str) -> list[sqlite3.Row]:
    """List runs for a document, most recent first."""
    cursor = conn.execute(
        "SELECT * FROM runs WHERE document_id = ? ORDER BY started_at DESC",
        (document_id,),
    )
    return cursor.fetchall()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

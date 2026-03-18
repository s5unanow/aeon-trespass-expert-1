"""Stage event recording in the registry."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast


def record_stage_start(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    stage_name: str,
    scope: str,
    entity_id: str,
    cache_key: str,
) -> int:
    """Record a stage invocation start. Returns the event_id."""
    cursor = conn.execute(
        "INSERT INTO stage_events (run_id, stage_name, scope, entity_id, cache_key,"
        " status, started_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, stage_name, scope, entity_id, cache_key, "started", _now_iso()),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def record_stage_finish(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    status: str = "completed",
    artifact_ref: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Mark a stage event as finished."""
    conn.execute(
        "UPDATE stage_events SET finished_at = ?, status = ?, artifact_ref = ?,"
        " error_message = ?, duration_ms = ? WHERE event_id = ?",
        (_now_iso(), status, artifact_ref, error_message, duration_ms, event_id),
    )
    conn.commit()


def find_cached_event(
    conn: sqlite3.Connection,
    *,
    cache_key: str,
) -> sqlite3.Row | None:
    """Find a completed stage event with matching cache key."""
    cursor = conn.execute(
        "SELECT * FROM stage_events WHERE cache_key = ? AND status = 'completed'"
        " ORDER BY finished_at DESC LIMIT 1",
        (cache_key,),
    )
    return cast("sqlite3.Row | None", cursor.fetchone())


def list_stage_events(
    conn: sqlite3.Connection,
    *,
    run_id: str,
) -> list[sqlite3.Row]:
    """List all stage events for a run, ordered by event_id."""
    cursor = conn.execute(
        "SELECT * FROM stage_events WHERE run_id = ? ORDER BY event_id",
        (run_id,),
    )
    return cursor.fetchall()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

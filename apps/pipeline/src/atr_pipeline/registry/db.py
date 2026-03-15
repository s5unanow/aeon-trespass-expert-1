"""SQLite registry — connection bootstrap and migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    qa_summary_ref TEXT
);

CREATE TABLE IF NOT EXISTS stage_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage_name TEXT NOT NULL,
    scope TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    artifact_ref TEXT,
    error_message TEXT,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_stage_events_run ON stage_events(run_id);
CREATE INDEX IF NOT EXISTS idx_stage_events_cache ON stage_events(cache_key);
CREATE INDEX IF NOT EXISTS idx_runs_document ON runs(document_id);
"""


def open_registry(path: Path) -> sqlite3.Connection:
    """Open or create the registry database and run migrations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    return conn

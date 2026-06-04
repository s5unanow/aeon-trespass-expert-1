"""Shared registry/artifact fixtures for the S5U-869 ref-bound export tests.

Both ``test_export_run.py`` (unit) and ``test_export_to_web_ref_binding.py``
(end-to-end) seed an identical SQLite registry + artifact-store layout; this
module is the single source of that scaffolding so neither test file carries
duplicated DDL or row-insert plumbing.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
    pipeline_version TEXT DEFAULT '1.0', config_hash TEXT DEFAULT 'h',
    started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running', qa_summary_ref TEXT,
    run_manifest_ref TEXT, git_commit TEXT DEFAULT '',
    source_pdf_sha256 TEXT DEFAULT '', edition TEXT DEFAULT 'all'
);
CREATE TABLE stage_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL, scope TEXT DEFAULT 'document',
    entity_id TEXT DEFAULT 'doc', cache_key TEXT DEFAULT 'k',
    status TEXT DEFAULT 'started', started_at TEXT NOT NULL,
    finished_at TEXT, artifact_ref TEXT
);
"""

# Sentinel: ``render_ref=NO_RENDER`` adds a run with no render stage event.
NO_RENDER = "\x00no-render\x00"


def init_registry(path: Path) -> sqlite3.Connection:
    """Create a registry DB with the minimal runs/stage_events schema."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def add_run(  # noqa: PLR0913 — keyword-only test fixture builder
    conn: sqlite3.Connection,
    *,
    run_id: str,
    started_at: str,
    document_id: str = "doc1",
    status: str = "completed",
    edition: str = "en",
    git_commit: str = "abc123def456",
    source_pdf_sha256: str = "pdfsha",
    qa_summary_ref: str | None = None,
    render_ref: str | None = NO_RENDER,
) -> None:
    """Insert a run row and (unless ``render_ref is NO_RENDER``) its render event."""
    finished = f"{started_at}.999" if status == "completed" else None
    conn.execute(
        "INSERT INTO runs (run_id, document_id, started_at, finished_at, status,"
        " edition, git_commit, source_pdf_sha256, qa_summary_ref)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            document_id,
            started_at,
            finished,
            status,
            edition,
            git_commit,
            source_pdf_sha256,
            qa_summary_ref,
        ),
    )
    if render_ref != NO_RENDER:
        conn.execute(
            "INSERT INTO stage_events (run_id, stage_name, status, started_at, artifact_ref)"
            " VALUES (?, 'render', 'completed', ?, ?)",
            (run_id, started_at, render_ref),
        )
    conn.commit()


def write_render_result(artifact_root: Path, ref: str, payload: dict) -> None:
    """Write a render-result artifact (the run's self-contained ref index)."""
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))

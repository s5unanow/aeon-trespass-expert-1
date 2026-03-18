"""Tests for the SQLite run registry."""

from pathlib import Path

from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import (
    find_cached_event,
    record_stage_finish,
    record_stage_start,
)
from atr_pipeline.registry.runs import (
    finish_run,
    get_run,
    list_runs,
    set_run_manifest_ref,
    start_run,
)


def test_migrations_bootstrap(tmp_path: Path) -> None:
    """Registry opens cleanly and creates tables."""
    conn = open_registry(tmp_path / "registry.db")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "runs" in tables
    assert "stage_events" in tables
    conn.close()


def test_run_lifecycle(tmp_path: Path) -> None:
    """Start and finish a run."""
    conn = open_registry(tmp_path / "registry.db")
    start_run(conn, run_id="run_01", document_id="doc", pipeline_version="0.1", config_hash="abc")

    run = get_run(conn, "run_01")
    assert run is not None
    assert run["status"] == "running"

    finish_run(conn, run_id="run_01", status="completed")
    run = get_run(conn, "run_01")
    assert run is not None
    assert run["status"] == "completed"
    conn.close()


def test_list_runs_by_document(tmp_path: Path) -> None:
    """List runs for a specific document."""
    conn = open_registry(tmp_path / "registry.db")
    start_run(conn, run_id="r1", document_id="doc1", pipeline_version="0.1", config_hash="a")
    start_run(conn, run_id="r2", document_id="doc1", pipeline_version="0.1", config_hash="b")
    start_run(conn, run_id="r3", document_id="doc2", pipeline_version="0.1", config_hash="c")

    runs = list_runs(conn, "doc1")
    assert len(runs) == 2
    conn.close()


def test_stage_event_lifecycle(tmp_path: Path) -> None:
    """Record and finish a stage event."""
    conn = open_registry(tmp_path / "registry.db")
    start_run(conn, run_id="run_01", document_id="doc", pipeline_version="0.1", config_hash="abc")

    event_id = record_stage_start(
        conn,
        run_id="run_01",
        stage_name="ingest",
        scope="document",
        entity_id="doc",
        cache_key="key123",
    )
    assert event_id is not None

    record_stage_finish(
        conn,
        event_id=event_id,
        status="completed",
        artifact_ref="doc/ingest/document/doc/hash.json",
        duration_ms=42,
    )

    cached = find_cached_event(conn, cache_key="key123")
    assert cached is not None
    assert cached["artifact_ref"] == "doc/ingest/document/doc/hash.json"
    conn.close()


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    """Non-existent cache key returns None."""
    conn = open_registry(tmp_path / "registry.db")
    cached = find_cached_event(conn, cache_key="nonexistent")
    assert cached is None
    conn.close()


def test_migration_adds_run_manifest_ref(tmp_path: Path) -> None:
    """Opening an old DB without run_manifest_ref adds the column."""
    import sqlite3

    db_path = tmp_path / "registry.db"
    raw = sqlite3.connect(str(db_path))
    raw.executescript("""
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            pipeline_version TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            qa_summary_ref TEXT
        );
        CREATE TABLE stage_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
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
    """)
    raw.execute("INSERT INTO runs VALUES ('r1','doc1','0.1','h','2026-01-01',NULL,'running',NULL)")
    raw.commit()
    raw.close()

    conn = open_registry(db_path)
    start_run(conn, run_id="r2", document_id="doc1", pipeline_version="0.1", config_hash="x")
    set_run_manifest_ref(conn, run_id="r2", ref="some/manifest.json")

    run = get_run(conn, "r2")
    assert run is not None
    assert run["run_manifest_ref"] == "some/manifest.json"
    conn.close()

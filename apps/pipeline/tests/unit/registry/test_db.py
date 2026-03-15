"""Tests for the SQLite run registry."""

from pathlib import Path

from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import (
    find_cached_event,
    record_stage_finish,
    record_stage_start,
)
from atr_pipeline.registry.runs import finish_run, get_run, list_runs, start_run


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

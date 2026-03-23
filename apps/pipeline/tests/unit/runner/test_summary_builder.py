"""Tests for RunSummaryV1 assembly from registry data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import finish_run, start_run
from atr_pipeline.runner.summary_builder import build_run_summary
from atr_schemas.run_summary_v1 import RunSummaryV1


def _setup_run(tmp_path: Path) -> sqlite3.Connection:
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        pipeline_version="0.1.0",
        config_hash="cfg_hash_12",
        git_commit="deadbeef" * 5,
        edition="all",
    )
    return conn


def test_summary_basic_fields(tmp_path: Path) -> None:
    """Summary captures run metadata from the registry."""
    conn = _setup_run(tmp_path)

    eid = record_stage_start(
        conn,
        run_id="run_abc123",
        stage_name="ingest",
        scope="document",
        entity_id="test_doc",
        cache_key="k1",
    )
    record_stage_finish(conn, event_id=eid, status="completed", duration_ms=500)

    finish_run(conn, run_id="run_abc123", status="completed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["ingest", "structure"],
    )
    assert isinstance(summary, RunSummaryV1)
    assert summary.run_id == "run_abc123"
    assert summary.document_id == "test_doc"
    assert summary.status == "completed"
    assert summary.pipeline_version == "0.1.0"
    assert summary.stages_requested == ["ingest", "structure"]
    assert summary.stages_completed == 1
    assert summary.stages_failed == 0
    assert summary.edition == "all"
    conn.close()


def test_summary_counts_page_events(tmp_path: Path) -> None:
    """Page-scoped events are aggregated into page counts."""
    conn = _setup_run(tmp_path)

    # Document-level stage event
    eid = record_stage_start(
        conn,
        run_id="run_abc123",
        stage_name="extract_native",
        scope="document",
        entity_id="test_doc",
        cache_key="k_doc",
    )
    record_stage_finish(conn, event_id=eid, status="completed", duration_ms=100)

    # Page-level events
    for page_id, status in [("p0001", "completed"), ("p0002", "cached"), ("p0003", "failed")]:
        eid = record_stage_start(
            conn,
            run_id="run_abc123",
            stage_name="extract_native",
            scope="page",
            entity_id=page_id,
            cache_key=f"k_{page_id}",
        )
        record_stage_finish(conn, event_id=eid, status=status, duration_ms=50)

    finish_run(conn, run_id="run_abc123", status="completed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["extract_native"],
    )
    assert summary.pages_total == 3
    assert summary.pages_processed == 2  # 3 total - 1 failed
    assert summary.pages_cached == 1
    assert summary.pages_failed == 1
    conn.close()


def test_summary_with_page_filter(tmp_path: Path) -> None:
    """Page filter is recorded in the summary."""
    conn = _setup_run(tmp_path)
    finish_run(conn, run_id="run_abc123", status="completed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["ingest"],
        page_filter=frozenset({"p0015", "p0018", "p0020"}),
    )
    assert summary.page_filter == ["p0015", "p0018", "p0020"]
    conn.close()


def test_summary_no_page_filter_is_none(tmp_path: Path) -> None:
    """Without a page filter, the field is None."""
    conn = _setup_run(tmp_path)
    finish_run(conn, run_id="run_abc123", status="completed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["ingest"],
    )
    assert summary.page_filter is None
    conn.close()


def test_summary_failed_stages(tmp_path: Path) -> None:
    """Failed stages are counted separately."""
    conn = _setup_run(tmp_path)

    eid1 = record_stage_start(
        conn,
        run_id="run_abc123",
        stage_name="ingest",
        scope="document",
        entity_id="test_doc",
        cache_key="k1",
    )
    record_stage_finish(conn, event_id=eid1, status="completed", duration_ms=100)

    eid2 = record_stage_start(
        conn,
        run_id="run_abc123",
        stage_name="structure",
        scope="document",
        entity_id="test_doc",
        cache_key="k2",
    )
    record_stage_finish(conn, event_id=eid2, status="failed", error_message="boom", duration_ms=50)

    finish_run(conn, run_id="run_abc123", status="failed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["ingest", "structure"],
    )
    assert summary.status == "failed"
    assert summary.stages_completed == 1
    assert summary.stages_failed == 1
    conn.close()


def test_summary_roundtrip_json(tmp_path: Path) -> None:
    """Summary can be serialized to JSON and parsed back."""
    conn = _setup_run(tmp_path)
    finish_run(conn, run_id="run_abc123", status="completed")

    summary = build_run_summary(
        conn,
        run_id="run_abc123",
        document_id="test_doc",
        stages_requested=["ingest"],
    )
    json_str = summary.model_dump_json()
    roundtrip = RunSummaryV1.model_validate_json(json_str)
    assert roundtrip.run_id == summary.run_id
    assert roundtrip.document_id == summary.document_id
    conn.close()

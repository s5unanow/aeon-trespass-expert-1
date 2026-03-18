"""Tests for QA blocking behavior and release gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.exceptions import Exit as ClickExit

from atr_pipeline.cli.commands.release import _check_qa_gate, _load_json_artifact
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, start_run
from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts


def _write_qa_summary(
    artifact_root: Path,
    *,
    blocking: bool,
    error_count: int = 0,
    critical_count: int = 0,
) -> str:
    """Write a QA summary artifact and return the ref path."""
    summary = QASummaryV1(
        document_id="doc1",
        run_id="run_1",
        counts=SeverityCounts(error=error_count, critical=critical_count),
        blocking=blocking,
    )
    ref_dir = artifact_root / "doc1" / "qa" / "document" / "doc1"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_dir / "abc123.json"
    ref_path.write_text(json.dumps(summary.model_dump(), indent=2), encoding="utf-8")
    return "doc1/qa/document/doc1/abc123.json"


def test_load_json_artifact(tmp_path: Path) -> None:
    """_load_json_artifact parses a persisted JSON artifact."""
    artifact_root = tmp_path / "artifacts"
    qa_ref = _write_qa_summary(artifact_root, blocking=True, error_count=2)

    data = _load_json_artifact(artifact_root, qa_ref)
    summary = QASummaryV1.model_validate(data)
    assert summary.blocking is True
    assert summary.counts.error == 2


def test_qa_gate_blocks_on_blocking_summary(tmp_path: Path) -> None:
    """_check_qa_gate raises Exit(1) when QA summary is blocking."""
    artifact_root = tmp_path / "artifacts"
    qa_ref = _write_qa_summary(artifact_root, blocking=True, error_count=3)
    run_data = {"qa_summary_ref": qa_ref, "run_manifest_ref": None}

    with pytest.raises(ClickExit) as exc_info:
        _check_qa_gate(artifact_root, run_data)
    assert exc_info.value.exit_code == 1


def test_qa_gate_passes_on_clean_summary(tmp_path: Path) -> None:
    """_check_qa_gate succeeds when QA summary is not blocking."""
    artifact_root = tmp_path / "artifacts"
    qa_ref = _write_qa_summary(artifact_root, blocking=False)
    run_data = {"qa_summary_ref": qa_ref, "run_manifest_ref": None}

    _check_qa_gate(artifact_root, run_data)


def test_qa_gate_skips_when_no_run_data() -> None:
    """_check_qa_gate skips gracefully when run_data is None."""
    _check_qa_gate(Path("/dummy"), None)


def test_qa_gate_skips_when_no_qa_ref(tmp_path: Path) -> None:
    """_check_qa_gate skips gracefully when run has no qa_summary_ref."""
    run_data = {"qa_summary_ref": None, "run_manifest_ref": None}

    _check_qa_gate(tmp_path, run_data)


def test_seed_run_with_qa_ref(tmp_path: Path) -> None:
    """Registry stores qa_summary_ref on the run record."""
    artifact_root = tmp_path / "artifacts"
    qa_ref = _write_qa_summary(artifact_root, blocking=False)

    conn = open_registry(tmp_path / "var" / "registry.db")
    start_run(
        conn,
        run_id="run_1",
        document_id="doc1",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    finish_run(conn, run_id="run_1", status="completed", qa_summary_ref=qa_ref)

    from atr_pipeline.registry.runs import get_run

    run = get_run(conn, "run_1")
    assert run is not None
    assert run["qa_summary_ref"] == qa_ref
    conn.close()

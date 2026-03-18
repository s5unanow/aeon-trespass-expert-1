"""Tests for QA blocking behavior and release gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.exceptions import Exit as ClickExit

from atr_pipeline.cli.commands.release import _check_qa_gate, _load_qa_summary
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, start_run
from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts


def _seed_run(
    tmp_path: Path,
    *,
    blocking: bool,
    error_count: int = 0,
    critical_count: int = 0,
) -> str:
    """Create a registry with a run that has a QA summary artifact."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    summary = QASummaryV1(
        document_id="doc1",
        run_id="run_1",
        counts=SeverityCounts(error=error_count, critical=critical_count),
        blocking=blocking,
    )
    ref_dir = artifact_root / "doc1" / "qa" / "document" / "doc1"
    ref_dir.mkdir(parents=True)
    ref_path = ref_dir / "abc123.json"
    ref_path.write_text(json.dumps(summary.model_dump(), indent=2), encoding="utf-8")

    qa_ref = "doc1/qa/document/doc1/abc123.json"

    conn = open_registry(tmp_path / "var" / "registry.db")
    start_run(
        conn,
        run_id="run_1",
        document_id="doc1",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    finish_run(conn, run_id="run_1", status="completed", qa_summary_ref=qa_ref)
    conn.close()

    return qa_ref


def test_load_qa_summary(tmp_path: Path) -> None:
    """_load_qa_summary parses a persisted QASummaryV1."""
    artifact_root = tmp_path / "artifacts"
    summary = QASummaryV1(
        document_id="doc1",
        run_id="run_1",
        counts=SeverityCounts(error=2),
        blocking=True,
    )
    ref_dir = artifact_root / "doc1" / "qa" / "document" / "doc1"
    ref_dir.mkdir(parents=True)
    ref_path = ref_dir / "abc.json"
    ref_path.write_text(json.dumps(summary.model_dump(), indent=2), encoding="utf-8")

    loaded = _load_qa_summary(artifact_root, "doc1/qa/document/doc1/abc.json")
    assert loaded.blocking is True
    assert loaded.counts.error == 2


def test_qa_gate_blocks_on_blocking_summary(tmp_path: Path) -> None:
    """_check_qa_gate raises Exit(1) when QA summary is blocking."""
    _seed_run(tmp_path, blocking=True, error_count=3)
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path

    with pytest.raises(ClickExit):
        _check_qa_gate(repo_root, artifact_root, "doc1")


def test_qa_gate_passes_on_clean_summary(tmp_path: Path) -> None:
    """_check_qa_gate succeeds when QA summary is not blocking."""
    _seed_run(tmp_path, blocking=False)
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path

    _check_qa_gate(repo_root, artifact_root, "doc1")


def test_qa_gate_skips_when_no_registry(tmp_path: Path) -> None:
    """_check_qa_gate skips gracefully when no registry exists."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    repo_root = tmp_path

    _check_qa_gate(repo_root, artifact_root, "doc1")


def test_qa_gate_skips_when_no_runs(tmp_path: Path) -> None:
    """_check_qa_gate skips gracefully when no runs exist."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    repo_root = tmp_path
    conn = open_registry(tmp_path / "var" / "registry.db")
    conn.close()

    _check_qa_gate(repo_root, artifact_root, "doc1")


def test_qa_gate_skips_when_no_qa_ref(tmp_path: Path) -> None:
    """_check_qa_gate skips gracefully when run has no qa_summary_ref."""
    repo_root = tmp_path
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    conn = open_registry(tmp_path / "var" / "registry.db")
    start_run(
        conn,
        run_id="run_1",
        document_id="doc1",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    finish_run(conn, run_id="run_1", status="completed")
    conn.close()

    _check_qa_gate(repo_root, artifact_root, "doc1")

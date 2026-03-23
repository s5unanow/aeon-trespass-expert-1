"""Tests for the atr runs-list and runs-show CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import finish_run, start_run

runner = CliRunner()


def _seed_db(tmp_path: Path) -> Path:
    """Create a registry with two runs and return the db path."""
    db_path = tmp_path / "var" / "registry.db"
    conn = open_registry(db_path)
    start_run(
        conn,
        run_id="run_aaa",
        document_id="doc1",
        pipeline_version="0.1.0",
        config_hash="cfg1",
    )
    eid = record_stage_start(
        conn,
        run_id="run_aaa",
        stage_name="ingest",
        scope="document",
        entity_id="doc1",
        cache_key="k1",
    )
    record_stage_finish(conn, event_id=eid, status="completed", duration_ms=100)
    finish_run(conn, run_id="run_aaa", status="completed")

    start_run(
        conn,
        run_id="run_bbb",
        document_id="doc2",
        pipeline_version="0.1.0",
        config_hash="cfg2",
    )
    finish_run(conn, run_id="run_bbb", status="failed")
    conn.close()
    return tmp_path


def _patch_repo_root(tmp_path: Path):  # type: ignore[no-untyped-def]
    return patch(
        "atr_pipeline.cli.commands.runs._find_repo_root",
        return_value=tmp_path,
    )


def test_runs_list_shows_all(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-list"])
    assert result.exit_code == 0
    assert "run_aaa" in result.stdout
    assert "run_bbb" in result.stdout


def test_runs_list_filter_by_doc(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-list", "--doc", "doc1"])
    assert result.exit_code == 0
    assert "run_aaa" in result.stdout
    assert "run_bbb" not in result.stdout


def test_runs_list_json_output(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2


def test_runs_show_detail(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-show", "run_aaa"])
    assert result.exit_code == 0
    assert "run_aaa" in result.stdout
    assert "completed" in result.stdout
    assert "ingest" in result.stdout


def test_runs_show_not_found(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-show", "run_nonexistent"])
    assert result.exit_code == 1


def test_runs_show_json_output(tmp_path: Path) -> None:
    root = _seed_db(tmp_path)
    with _patch_repo_root(root):
        result = runner.invoke(app, ["runs-show", "run_aaa", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["run_id"] == "run_aaa"
    assert "stages" in data

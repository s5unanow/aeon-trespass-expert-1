"""Integration test: page-subset run with --pages filter.

The walking skeleton PDF has 3 pages. This verifies that --pages 1 only
processes page 1, leaving other page artifacts untouched.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry as _real_open_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    stdout: str
    artifact_root: Path
    registry_path: Path


@pytest.fixture(scope="module")
def page_filter_run(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """Run pipeline with --pages 1 --edition en."""
    tmp = tmp_path_factory.mktemp("page_filter")
    artifact_root = tmp / "artifacts"
    registry_path = tmp / "var" / "registry.db"

    repo = _repo_root()
    real_config = load_document_config("walking_skeleton", repo_root=repo)
    patched_config = real_config.model_copy(update={"artifact_root": artifact_root})

    runner = CliRunner()
    with (
        patch(
            "atr_pipeline.cli.commands.run.load_document_config",
            return_value=patched_config,
        ),
        patch(
            "atr_pipeline.cli.commands.run.open_registry",
            side_effect=lambda _: _real_open_registry(registry_path),
        ),
    ):
        result = runner.invoke(
            app,
            ["run", "--doc", "walking_skeleton", "--edition", "en", "--pages", "1"],
        )

    return RunResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        artifact_root=artifact_root,
        registry_path=registry_path,
    )


def _query_db(path: Path, sql: str) -> list[Any]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_page_filter_exits_zero(page_filter_run: RunResult) -> None:
    """Page-filtered run exits 0."""
    assert page_filter_run.exit_code == 0, (
        f"CLI exited {page_filter_run.exit_code}:\n{page_filter_run.stdout}"
    )


def test_page_filter_echoes_filter(page_filter_run: RunResult) -> None:
    """CLI output shows the page filter."""
    assert "p0001" in page_filter_run.stdout


def test_page_filter_only_processes_page_1(page_filter_run: RunResult) -> None:
    """Only page 1 gets render artifacts, not pages 2-3."""
    render_dir = page_filter_run.artifact_root / "walking_skeleton" / "render_page.v1" / "page"
    if render_dir.exists():
        rendered = sorted(d.name for d in render_dir.iterdir() if d.is_dir())
        assert "p0001" in rendered
        assert "p0002" not in rendered
        assert "p0003" not in rendered


def test_page_filter_run_completes(page_filter_run: RunResult) -> None:
    """Run record is completed."""
    rows = _query_db(page_filter_run.registry_path, "SELECT * FROM runs")
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"

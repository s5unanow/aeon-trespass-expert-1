"""Integration test: source-only (edition=en) pipeline run.

Verifies that ``atr run --doc walking_skeleton --edition en`` completes
without running the translate stage, and produces EN-only artifacts.
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
def source_only_run(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """Run the pipeline in source-only mode."""
    tmp = tmp_path_factory.mktemp("source_only")
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
        result = runner.invoke(app, ["run", "--doc", "walking_skeleton", "--edition", "en"])

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


def test_source_only_exits_zero(source_only_run: RunResult) -> None:
    """Source-only pipeline exits 0."""
    assert source_only_run.exit_code == 0, (
        f"CLI exited {source_only_run.exit_code}:\n{source_only_run.stdout}"
    )
    assert "completed successfully" in source_only_run.stdout


def test_source_only_skips_translate(source_only_run: RunResult) -> None:
    """Translate stage is not present in the output."""
    assert "[translate]" not in source_only_run.stdout


def test_source_only_runs_render(source_only_run: RunResult) -> None:
    """Render stage runs in source-only mode."""
    assert "[render]" in source_only_run.stdout


def test_source_only_no_translate_event(source_only_run: RunResult) -> None:
    """No translate stage event exists in the registry."""
    events = _query_db(
        source_only_run.registry_path,
        "SELECT * FROM stage_events WHERE stage_name='translate'",
    )
    assert len(events) == 0


def test_source_only_edition_in_run_record(source_only_run: RunResult) -> None:
    """Run record stores edition='en'."""
    rows = _query_db(source_only_run.registry_path, "SELECT * FROM runs")
    assert len(rows) == 1
    assert rows[0]["edition"] == "en"


def test_source_only_no_ru_ir(source_only_run: RunResult) -> None:
    """No RU IR artifacts exist."""
    ru_dir = source_only_run.artifact_root / "walking_skeleton" / "page_ir.v1.ru"
    assert not ru_dir.exists()

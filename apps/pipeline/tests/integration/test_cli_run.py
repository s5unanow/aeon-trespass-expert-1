"""Integration test: CLI run command — full pipeline execution.

Invokes ``atr run --doc walking_skeleton`` through the Typer CliRunner
and verifies exit code, artifact output, and registry records.
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

_EXPECTED_STAGES = frozenset(
    {
        "ingest",
        "extract_native",
        "extract_layout",
        "symbols",
        "structure",
        "translate",
        "render",
        "qa",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class RunResult:
    """Captured result of a CLI pipeline run."""

    exit_code: int
    stdout: str
    artifact_root: Path
    registry_path: Path


@pytest.fixture(scope="module")
def cli_run(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """Run the full pipeline once and cache the result for all tests."""
    tmp = tmp_path_factory.mktemp("cli_run")
    artifact_root = tmp / "artifacts"
    registry_path = tmp / "var" / "registry.db"

    repo = _repo_root()
    real_config = load_document_config("walking_skeleton", repo_root=repo)
    patched_config = real_config.model_copy(
        update={"artifact_root": artifact_root},
    )

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
        result = runner.invoke(app, ["run", "--doc", "walking_skeleton"])

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


def test_cli_run_exits_zero(cli_run: RunResult) -> None:
    """Full pipeline run via CLI exits 0."""
    assert cli_run.exit_code == 0, f"CLI exited {cli_run.exit_code}:\n{cli_run.stdout}"
    assert "completed successfully" in cli_run.stdout


def test_cli_run_produces_artifacts(cli_run: RunResult) -> None:
    """Run produces JSON artifacts under the artifact root."""
    artifacts = list(cli_run.artifact_root.glob("walking_skeleton/**/*.json"))
    assert len(artifacts) > 0, "No artifacts produced"


def test_cli_run_records_completed_run(cli_run: RunResult) -> None:
    """Registry DB contains a completed run record."""
    rows = _query_db(cli_run.registry_path, "SELECT * FROM runs")
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["document_id"] == "walking_skeleton"


def test_cli_run_records_all_stage_events(cli_run: RunResult) -> None:
    """Each expected stage has a completed event in the registry."""
    events = _query_db(
        cli_run.registry_path,
        "SELECT * FROM stage_events WHERE status='completed'",
    )
    actual = {e["stage_name"] for e in events}
    assert actual == _EXPECTED_STAGES


def test_cli_run_stage_output_echoed(cli_run: RunResult) -> None:
    """CLI output lists each stage name during execution."""
    for stage in _EXPECTED_STAGES:
        assert f"[{stage}]" in cli_run.stdout

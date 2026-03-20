"""Integration test: partial pipeline runs via --from/--to.

Exercises ``atr run --doc walking_skeleton --from X --to Y`` through
the Typer CliRunner and verifies that only the requested stage range
executes, plus the error path for invalid stage names.
"""

from __future__ import annotations

import shutil
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


def _invoke_run(
    tmp: Path,
    extra_args: list[str],
) -> RunResult:
    """Run CLI with extra args and return captured result."""
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
            ["run", "--doc", "walking_skeleton", *extra_args],
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


def _completed_stages(registry_path: Path) -> set[str]:
    events = _query_db(
        registry_path,
        "SELECT stage_name FROM stage_events WHERE status='completed'",
    )
    return {e["stage_name"] for e in events}


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy a directory tree."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


# ── Full prerequisite run (cached for the partial-from tests) ─────────


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """Run the full pipeline once so partial --from runs have artifacts."""
    tmp = tmp_path_factory.mktemp("partial_full")
    return _invoke_run(tmp, ["--edition", "en"])


# ── --from structure --to render ──────────────────────────────────────


@pytest.fixture(scope="module")
def structure_to_render(
    full_run: RunResult,
    tmp_path_factory: pytest.TempPathFactory,
) -> RunResult:
    """Partial run from structure to render, reusing full-run artifacts."""
    tmp = tmp_path_factory.mktemp("partial_structure_render")
    # Copy artifacts from full run so the partial run can read them
    _copy_tree(full_run.artifact_root, tmp / "artifacts")
    return _invoke_run(tmp, ["--from", "structure", "--to", "render", "--edition", "en"])


def test_structure_to_render_exits_zero(structure_to_render: RunResult) -> None:
    assert structure_to_render.exit_code == 0, (
        f"CLI exited {structure_to_render.exit_code}:\n{structure_to_render.stdout}"
    )


def test_structure_to_render_runs_correct_stages(
    structure_to_render: RunResult,
) -> None:
    """Only structure and render stages should have completed events."""
    actual = _completed_stages(structure_to_render.registry_path)
    assert actual == {"structure", "render"}


def test_structure_to_render_echoes_stages(structure_to_render: RunResult) -> None:
    assert "[structure]" in structure_to_render.stdout
    assert "[render]" in structure_to_render.stdout
    assert "[ingest]" not in structure_to_render.stdout
    assert "[qa]" not in structure_to_render.stdout


# ── --from qa --to qa (single stage) ─────────────────────────────────


@pytest.fixture(scope="module")
def qa_only(
    full_run: RunResult,
    tmp_path_factory: pytest.TempPathFactory,
) -> RunResult:
    """Partial run of just the QA stage."""
    tmp = tmp_path_factory.mktemp("partial_qa")
    _copy_tree(full_run.artifact_root, tmp / "artifacts")
    return _invoke_run(tmp, ["--from", "qa", "--to", "qa", "--edition", "en"])


def test_qa_only_exits_zero(qa_only: RunResult) -> None:
    assert qa_only.exit_code == 0, f"CLI exited {qa_only.exit_code}:\n{qa_only.stdout}"


def test_qa_only_runs_single_stage(qa_only: RunResult) -> None:
    actual = _completed_stages(qa_only.registry_path)
    assert actual == {"qa"}


def test_qa_only_echoes_single_stage(qa_only: RunResult) -> None:
    assert "[qa]" in qa_only.stdout
    assert "[structure]" not in qa_only.stdout


# ── Invalid stage name ────────────────────────────────────────────────


def test_invalid_from_stage_fails(tmp_path: Path) -> None:
    """--from with an invalid stage name should exit non-zero."""
    result = _invoke_run(tmp_path, ["--from", "nonexistent"])
    assert result.exit_code != 0


def test_invalid_to_stage_fails(tmp_path: Path) -> None:
    """--to with an invalid stage name should exit non-zero."""
    result = _invoke_run(tmp_path, ["--to", "nonexistent"])
    assert result.exit_code != 0

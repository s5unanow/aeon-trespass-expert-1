"""Unit tests for the run command executor loop.

Tests stage registry resolution, failure stops execution, and cache hit
echoing. All heavy dependencies (config, stages, artifact store) are mocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.runner.result import StageResult
from atr_pipeline.store.artifact_ref import ArtifactRef

runner = CliRunner()

_MOD = "atr_pipeline.cli.commands.run"


@dataclass(frozen=True)
class CLIRunResult:
    """Wrapper around CliRunner result with captured mock references."""

    exit_code: int
    stdout: str
    finish_mock: Any


def _ok(name: str, *, cached: bool = False) -> StageResult:
    ref = ArtifactRef(
        document_id="d",
        schema_family=name,
        scope="document",
        entity_id="d",
        content_hash="abc123",
    )
    return StageResult(stage_name=name, cache_key="k", cached=cached, artifact_ref=ref)


def _fail(name: str) -> StageResult:
    return StageResult(stage_name=name, cache_key="k", cached=False, error="boom")


def _mock_config(tmp: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.artifact_root = tmp / "artifacts"
    cfg.repo_root = tmp
    cfg.pipeline.version = "0.1.0"
    cfg.model_dump.return_value = {"x": 1}
    return cfg


def _run_with(
    stage_names: list[str],
    results: list[StageResult],
    tmp_path: Path,
) -> CLIRunResult:
    """Invoke ``atr run`` with mocked stages returning *results*."""
    cfg = _mock_config(tmp_path)
    registry = {n: MagicMock(name=n) for n in stage_names}
    result_iter = iter(results)

    with (
        patch(f"{_MOD}.load_document_config", return_value=cfg),
        patch(f"{_MOD}.open_registry"),
        patch(f"{_MOD}.ArtifactStore"),
        patch(f"{_MOD}.start_run"),
        patch(f"{_MOD}.finish_run") as finish_mock,
        patch(f"{_MOD}.build_run_manifest", return_value={}),
        patch(f"{_MOD}.set_run_manifest_ref"),
        patch(f"{_MOD}.build_stage_registry", return_value=registry),
        patch(f"{_MOD}.resolve_stage_range", return_value=stage_names),
        patch(
            f"{_MOD}.execute_stage",
            side_effect=lambda *a, **kw: next(result_iter),
        ),
    ):
        cli_result = runner.invoke(app, ["run", "--doc", "test"])

    return CLIRunResult(
        exit_code=cli_result.exit_code,
        stdout=cli_result.stdout,
        finish_mock=finish_mock,
    )


def test_run_resolves_stages_from_registry(tmp_path: Path) -> None:
    """Run command echoes each resolved stage name."""
    names = ["ingest", "structure"]
    result = _run_with(names, [_ok(n) for n in names], tmp_path)
    assert result.exit_code == 0
    assert "[ingest]" in result.stdout
    assert "[structure]" in result.stdout


def test_run_stops_on_stage_failure(tmp_path: Path) -> None:
    """When a stage fails the loop breaks and CLI exits 1."""
    result = _run_with(
        ["ingest", "structure", "render"],
        [_ok("ingest"), _fail("structure")],
        tmp_path,
    )
    assert result.exit_code == 1
    assert "[render]" not in result.stdout
    assert "finished with errors" in result.stdout


def test_run_echoes_cached_stages(tmp_path: Path) -> None:
    """Cached stages are echoed with '(cached)' marker."""
    result = _run_with(
        ["ingest", "structure"],
        [_ok("ingest", cached=True), _ok("structure")],
        tmp_path,
    )
    assert result.exit_code == 0
    assert "(cached)" in result.stdout
    assert "completed successfully" in result.stdout


def test_run_records_completed_status(tmp_path: Path) -> None:
    """Successful run calls finish_run with 'completed'."""
    result = _run_with(["ingest"], [_ok("ingest")], tmp_path)
    result.finish_mock.assert_called_once()
    assert result.finish_mock.call_args.kwargs["status"] == "completed"


def test_run_records_failed_status_on_error(tmp_path: Path) -> None:
    """Failed run calls finish_run with 'failed'."""
    result = _run_with(["ingest"], [_fail("ingest")], tmp_path)
    result.finish_mock.assert_called_once()
    assert result.finish_mock.call_args.kwargs["status"] == "failed"

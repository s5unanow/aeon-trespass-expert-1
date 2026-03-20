"""Tests for the eval CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_schemas.page_ir_v1 import HeadingBlock, IconInline, PageIRV1, ParagraphBlock

runner = CliRunner()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _write_golden_ir(artifacts_root: Path, document_id: str, page_id: str) -> None:
    """Write a synthetic page IR that matches the core golden set."""
    ir = PageIRV1(
        document_id=document_id,
        page_id=page_id,
        page_number=1,
        language="en",
        blocks=[
            HeadingBlock(
                block_id="p0001.b001",
                children=[IconInline(symbol_id="sym_001")],
            ),
            ParagraphBlock(block_id="p0001.b002"),
        ],
        reading_order=["p0001.b001", "p0001.b002"],
    )
    ir_dir = artifacts_root / document_id / "page_ir.v1.en" / "page" / page_id
    ir_dir.mkdir(parents=True, exist_ok=True)
    (ir_dir / "test.json").write_text(json.dumps(json.loads(ir.model_dump_json()), indent=2))


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_eval_help() -> None:
    """eval --help works."""
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "golden-set" in _strip_ansi(result.output)


def test_eval_doc_is_optional() -> None:
    """eval accepts --golden-set without --doc (doc inferred from golden set)."""
    result = runner.invoke(app, ["eval", "--help"])
    # --doc should not be marked as required in help output
    help_text = _strip_ansi(result.output)
    assert "--doc" in help_text
    # Verify we can invoke with just --golden-set (will fail on golden set lookup, not arg parse)
    result = runner.invoke(app, ["eval", "--golden-set", "nonexistent"])
    # Should fail because golden set doesn't exist, NOT because --doc is missing
    assert result.exit_code != 0
    assert "Missing option" not in _strip_ansi(result.output)


def test_eval_golden_set_all_accepted_without_doc(tmp_path: Path) -> None:
    """eval --golden-set all runs without --doc."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with (
        patch(
            "atr_pipeline.cli.commands.eval_cmd.load_document_config",
            return_value=patched_config,
        ),
        patch(
            "atr_pipeline.cli.commands.eval_cmd.discover_golden_sets",
            return_value=["core"],
        ),
    ):
        result = runner.invoke(app, ["eval", "--golden-set", "all"])

    output = _strip_ansi(result.output)
    assert "Missing option" not in output
    assert "Running 1 golden set(s)" in output


def test_eval_missing_golden_set() -> None:
    """eval with non-existent golden set fails."""
    result = runner.invoke(
        app, ["eval", "--golden-set", "nonexistent", "--doc", "walking_skeleton"]
    )
    assert result.exit_code != 0


def test_eval_with_output_json(tmp_path: Path) -> None:
    """eval writes JSON report when --output-json is specified."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        output_json = tmp_path / "report.json"
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0, result.output
    assert output_json.exists()
    report_data = json.loads(output_json.read_text())
    assert report_data["passed"] is True


def test_eval_fail_on_threshold_passing(tmp_path: Path) -> None:
    """eval --fail-on-threshold exits 0 when all thresholds pass."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--fail-on-threshold",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "THRESHOLD" in _strip_ansi(result.output)


def test_eval_fail_on_threshold_reports_values(tmp_path: Path) -> None:
    """eval --fail-on-threshold includes threshold table in output."""
    artifacts = tmp_path / "artifacts"
    _write_golden_ir(artifacts, "walking_skeleton", "p0001")

    real_config = load_document_config("walking_skeleton", repo_root=_repo_root())
    patched_config = real_config.model_copy(update={"artifact_root": artifacts})

    with patch(
        "atr_pipeline.cli.commands.eval_cmd.load_document_config",
        return_value=patched_config,
    ):
        output_json = tmp_path / "report.json"
        result = runner.invoke(
            app,
            [
                "eval",
                "--golden-set",
                "core",
                "--doc",
                "walking_skeleton",
                "--fail-on-threshold",
                "--output-json",
                str(output_json),
            ],
        )

    assert result.exit_code == 0, result.output
    report_data = json.loads(output_json.read_text())
    assert "threshold_results" in report_data
    assert len(report_data["threshold_results"]) > 0

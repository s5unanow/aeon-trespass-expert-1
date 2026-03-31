"""Tests for the atr bench CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from atr_pipeline.cli.main import app

runner = CliRunner()


class TestBenchHelp:
    def test_help_shows_options(self) -> None:
        result = runner.invoke(app, ["bench", "--help"])
        assert result.exit_code == 0
        assert "--ladder" in result.output
        assert "--output-json" in result.output
        assert "--baseline" in result.output
        assert "--fail-on-regression" in result.output


class TestBenchErrors:
    def test_nonexistent_ladder(self) -> None:
        result = runner.invoke(app, ["bench", "--ladder", "nonexistent_ladder_xyz"])
        assert result.exit_code != 0

    def test_nonexistent_baseline(self, tmp_path: Path) -> None:
        fake = tmp_path / "no_such_file.json"
        result = runner.invoke(app, ["bench", "--baseline", str(fake)])
        assert result.exit_code != 0

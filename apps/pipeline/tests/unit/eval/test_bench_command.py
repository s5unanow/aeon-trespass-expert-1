"""Tests for the atr bench CLI command."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from atr_pipeline.cli.main import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestBenchHelp:
    def test_help_shows_options(self) -> None:
        result = runner.invoke(app, ["bench", "--help"])
        assert result.exit_code == 0
        text = _strip_ansi(result.output)
        assert "--ladder" in text
        assert "--output-json" in text
        assert "--baseline" in text
        assert "--fail-on-regression" in text


class TestBenchErrors:
    def test_nonexistent_ladder(self) -> None:
        result = runner.invoke(app, ["bench", "--ladder", "nonexistent_ladder_xyz"])
        assert result.exit_code != 0

    def test_nonexistent_baseline(self, tmp_path: Path) -> None:
        fake = tmp_path / "no_such_file.json"
        result = runner.invoke(app, ["bench", "--baseline", str(fake)])
        assert result.exit_code != 0

"""Smoke test: CLI entrypoint loads without error."""

from typer.testing import CliRunner

from atr_pipeline.cli.main import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "atr-pipeline" in result.stdout


def test_version_command() -> None:
    result = runner.invoke(app, ["version-cmd"])
    assert result.exit_code == 0
    assert "atr-pipeline" in result.stdout


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "document compiler" in result.stdout

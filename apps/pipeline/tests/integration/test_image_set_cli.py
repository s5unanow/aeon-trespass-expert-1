"""Real ``atr ingest`` proof for the committed image-set fixture."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry as real_open_registry

runner = CliRunner()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_atr_ingest_image_set_writes_raw_artifacts_once(tmp_path: Path) -> None:
    config = load_document_config("image_set_sample", repo_root=_repo_root())
    config.artifact_root = tmp_path / "artifacts"

    def _isolated_registry(_path: Path) -> sqlite3.Connection:
        return real_open_registry(tmp_path / "registry.db")

    with (
        patch(
            "atr_pipeline.cli.commands.ingest.load_document_config",
            return_value=config,
        ),
        patch(
            "atr_pipeline.cli.commands.ingest.open_registry",
            side_effect=_isolated_registry,
        ),
    ):
        first = runner.invoke(app, ["ingest", "--doc", "image_set_sample"])
        raw_files = sorted((tmp_path / "artifacts/image_set_sample/raw_image").rglob("*.png"))
        first_mtimes = {path: path.stat().st_mtime_ns for path in raw_files}
        second = runner.invoke(app, ["ingest", "--doc", "image_set_sample"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    assert "Ingest completed" in first.stdout
    assert len(raw_files) == 2
    assert sorted((tmp_path / "artifacts/image_set_sample/raw_image").rglob("*.png")) == raw_files
    assert {path: path.stat().st_mtime_ns for path in raw_files} == first_mtimes

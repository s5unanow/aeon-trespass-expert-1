"""Tests for the `atr patch` CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config import load_document_config
from atr_pipeline.store.artifact_store import ArtifactStore

runner = CliRunner()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _setup_artifact(tmp: Path, doc: str = "walking_skeleton") -> tuple[Path, str]:
    """Create a minimal artifact and return (artifact_root, ref_path)."""
    store = ArtifactStore(tmp / "artifacts")
    data = {"blocks": [{"block_id": "b1", "text": "original"}]}
    ref = store.put_json(
        document_id=doc,
        schema_family="page_ir.v1.ru",
        scope="page",
        entity_id="p0001",
        data=data,
    )
    return tmp / "artifacts", ref.relative_path


def _write_patch(tmp: Path, ref_path: str) -> Path:
    """Write a valid patch file and return its path."""
    patch_data = {
        "schema_version": "patch_set.v1",
        "patch_id": "test-patch-1",
        "target_artifact_ref": ref_path,
        "operations": [
            {"op": "replace", "path": "/blocks/0/text", "value": "patched"},
        ],
        "reason": "test fix",
        "author": "test",
    }
    p = tmp / "patch.json"
    p.write_text(json.dumps(patch_data))
    return p


def _invoke_patch(
    tmp: Path,
    artifact_root: Path,
    patch_file: Path,
    extra_args: list[str] | None = None,
) -> Result:
    """Invoke `atr patch` with patched config."""
    repo = _repo_root()
    real_config = load_document_config("walking_skeleton", repo_root=repo)
    patched_config = real_config.model_copy(update={"artifact_root": artifact_root})

    args = ["patch", "--doc", "walking_skeleton", "--patch-file", str(patch_file)]
    if extra_args:
        args.extend(extra_args)

    with patch(
        "atr_pipeline.cli.commands.patch.load_document_config",
        return_value=patched_config,
    ):
        return runner.invoke(app, args)


def test_patch_applies_and_stores(tmp_path: Path) -> None:
    """Patch command should apply operations and store the result."""
    artifact_root, ref_path = _setup_artifact(tmp_path)
    patch_file = _write_patch(tmp_path, ref_path)

    result = _invoke_patch(tmp_path, artifact_root, patch_file)
    assert result.exit_code == 0, f"CLI exited {result.exit_code}:\n{result.output}"
    assert "Stored patched artifact" in result.output

    # Verify the new artifact was stored
    artifact_dir = artifact_root / "walking_skeleton" / "page_ir.v1.ru" / "page" / "p0001"
    jsons = sorted(artifact_dir.glob("*.json"))
    assert len(jsons) == 2  # original + patched

    newest = json.loads(jsons[-1].read_text())
    assert newest["blocks"][0]["text"] == "patched"


def test_patch_missing_file(tmp_path: Path) -> None:
    """Patch command should fail if patch file doesn't exist."""
    result = runner.invoke(
        app,
        ["patch", "--doc", "walking_skeleton", "--patch-file", "/nonexistent.json"],
    )
    assert result.exit_code != 0


def test_patch_missing_artifact(tmp_path: Path) -> None:
    """Patch command should fail if target artifact doesn't exist."""
    patch_data = {
        "schema_version": "patch_set.v1",
        "patch_id": "bad-ref",
        "target_artifact_ref": "walking_skeleton/page_ir.v1.ru/page/p9999/deadbeef.json",
        "operations": [{"op": "replace", "path": "/x", "value": 1}],
    }
    pf = tmp_path / "bad_patch.json"
    pf.write_text(json.dumps(patch_data))

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    result = _invoke_patch(tmp_path, artifact_root, pf)
    assert result.exit_code != 0
    assert "not found" in result.output


def test_patch_no_target_ref(tmp_path: Path) -> None:
    """Patch command should fail if target_artifact_ref is empty."""
    patch_data = {
        "schema_version": "patch_set.v1",
        "patch_id": "no-ref",
        "target_artifact_ref": "",
        "operations": [],
    }
    pf = tmp_path / "no_ref.json"
    pf.write_text(json.dumps(patch_data))

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    result = _invoke_patch(tmp_path, artifact_root, pf)
    assert result.exit_code != 0

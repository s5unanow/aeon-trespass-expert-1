"""Tests for scripts/export_assistant_to_web.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "export_assistant_to_web.py"


@pytest.fixture()
def export_mod() -> Iterator[ModuleType]:
    """Import export_assistant_to_web.py as a module."""
    spec = importlib.util.spec_from_file_location("export_assistant_to_web", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_assistant_to_web"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("export_assistant_to_web", None)


def test_export_copies_index_and_manifest(tmp_path: Path, export_mod: ModuleType) -> None:
    """Export copies assistant_index.sqlite and manifest to web public."""
    doc_id = "test_doc"
    edition = "en"

    # Set up fake artifact tree
    index_dir = tmp_path / "artifacts" / doc_id / f"assistant_index.{edition}" / "document" / doc_id
    index_dir.mkdir(parents=True)
    db_file = index_dir / "assistant_index.sqlite"
    db_file.write_bytes(b"fake-sqlite-db")

    manifest_dir = tmp_path / "artifacts" / doc_id / "assistant_pack.v1" / "document" / doc_id
    manifest_dir.mkdir(parents=True)
    manifest = {"document_id": doc_id, "edition": edition, "chunks_count": 42}
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

    web_docs = tmp_path / "web" / "public" / "documents"

    # Patch module-level paths
    export_mod.ARTIFACT_ROOT = tmp_path / "artifacts"
    export_mod.DOCUMENTS_ROOT = web_docs

    result = export_mod.export_assistant(doc_id, edition)
    assert result is True

    data_dir = web_docs / doc_id / edition / "data"
    assert (data_dir / "assistant_index.sqlite").exists()
    assert (data_dir / "assistant_index.sqlite").read_bytes() == b"fake-sqlite-db"
    assert (data_dir / "assistant_pack.json").exists()
    exported = json.loads((data_dir / "assistant_pack.json").read_text())
    assert exported["chunks_count"] == 42


def test_export_returns_false_when_no_artifacts(tmp_path: Path, export_mod: ModuleType) -> None:
    """Export returns False when no assistant artifacts exist."""
    export_mod.ARTIFACT_ROOT = tmp_path / "artifacts"
    export_mod.DOCUMENTS_ROOT = tmp_path / "web"

    result = export_mod.export_assistant("no_doc", "en")
    assert result is False

"""Tests for manifest-driven artifact ref extraction in release command."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.cli.commands.release import _extract_render_refs


def _write_artifact(artifact_root: Path, ref: str, data: dict[str, object]) -> None:
    """Write a JSON artifact at the given ref path."""
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_extract_render_refs_from_manifest(tmp_path: Path) -> None:
    """Render page refs are extracted from the manifest's render stage artifact."""
    artifact_root = tmp_path / "artifacts"

    render_result = {
        "document_id": "doc1",
        "pages_rendered": 2,
        "page_refs": {
            "p1": "doc1/render_page.v1/page/p1/abc.json",
            "p2": "doc1/render_page.v1/page/p2/def.json",
        },
    }
    render_ref = "doc1/render/document/doc1/render_hash.json"
    _write_artifact(artifact_root, render_ref, render_result)

    manifest_data = {
        "schema_version": "run_manifest.v1",
        "run_id": "run_1",
        "stages": [
            {
                "stage_name": "render",
                "scope": "document",
                "entity_id": "doc1",
                "cache_key": "abc",
                "status": "completed",
                "artifact_ref": render_ref,
            },
        ],
    }
    manifest_ref = "doc1/run_manifest.v1/run/run_1/manifest_hash.json"
    _write_artifact(artifact_root, manifest_ref, manifest_data)

    run_data = {"qa_summary_ref": None, "run_manifest_ref": manifest_ref}
    refs = _extract_render_refs(artifact_root, run_data)

    assert refs is not None
    assert refs["p1"] == "doc1/render_page.v1/page/p1/abc.json"
    assert refs["p2"] == "doc1/render_page.v1/page/p2/def.json"


def test_extract_render_refs_returns_none_without_run_data(tmp_path: Path) -> None:
    """Returns None when run_data is None."""
    assert _extract_render_refs(tmp_path, None) is None


def test_extract_render_refs_returns_none_without_manifest_ref(tmp_path: Path) -> None:
    """Returns None when run has no manifest ref."""
    run_data = {"qa_summary_ref": None, "run_manifest_ref": None}
    assert _extract_render_refs(tmp_path, run_data) is None


def test_extract_render_refs_returns_none_without_render_stage(tmp_path: Path) -> None:
    """Returns None when manifest has no render stage."""
    artifact_root = tmp_path / "artifacts"

    manifest_data = {
        "schema_version": "run_manifest.v1",
        "run_id": "run_1",
        "stages": [
            {
                "stage_name": "ingest",
                "scope": "document",
                "entity_id": "doc1",
                "cache_key": "abc",
                "status": "completed",
                "artifact_ref": "some/ref.json",
            },
        ],
    }
    manifest_ref = "doc1/run_manifest.v1/run/run_1/mh.json"
    _write_artifact(artifact_root, manifest_ref, manifest_data)

    run_data = {"qa_summary_ref": None, "run_manifest_ref": manifest_ref}
    assert _extract_render_refs(artifact_root, run_data) is None

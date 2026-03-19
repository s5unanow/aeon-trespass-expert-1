"""Tests for manifest-driven artifact ref extraction in release command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.exceptions import Exit

from atr_pipeline.cli.commands.release import _extract_artifact_refs


def _write_artifact(artifact_root: Path, ref: str, data: dict[str, object]) -> None:
    """Write a JSON artifact at the given ref path."""
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_extract_artifact_refs_from_manifest(tmp_path: Path) -> None:
    """Render page refs and companion refs are extracted from the manifest."""
    artifact_root = tmp_path / "artifacts"

    render_result = {
        "document_id": "doc1",
        "pages_rendered": 2,
        "page_refs": {
            "p1": "doc1/render_page.v1/page/p1/abc.json",
            "p2": "doc1/render_page.v1/page/p2/def.json",
        },
        "glossary_ref": "doc1/glossary_payload.v1/document/doc1/gh.json",
        "search_docs_ref": "doc1/search_docs.v1/document/doc1/sh.json",
        "nav_ref": "doc1/nav.v1/document/doc1/nh.json",
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
    page_refs, companion_refs, _image_refs = _extract_artifact_refs(artifact_root, run_data)

    assert page_refs["p1"] == "doc1/render_page.v1/page/p1/abc.json"
    assert page_refs["p2"] == "doc1/render_page.v1/page/p2/def.json"
    assert companion_refs["glossary_ref"] == "doc1/glossary_payload.v1/document/doc1/gh.json"
    assert companion_refs["nav_ref"] == "doc1/nav.v1/document/doc1/nh.json"


def test_extract_artifact_refs_exits_without_manifest_ref(tmp_path: Path) -> None:
    """Exits when run has no manifest ref."""
    run_data = {"qa_summary_ref": None, "run_manifest_ref": None}
    with pytest.raises(Exit):
        _extract_artifact_refs(tmp_path, run_data)


def test_extract_artifact_refs_exits_without_render_stage(tmp_path: Path) -> None:
    """Exits when manifest has no render stage."""
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
    with pytest.raises(Exit):
        _extract_artifact_refs(artifact_root, run_data)


def test_extract_companion_refs_partial(tmp_path: Path) -> None:
    """Companion refs are extracted only for keys present in render result."""
    artifact_root = tmp_path / "artifacts"

    render_result = {
        "document_id": "doc1",
        "pages_rendered": 1,
        "page_refs": {"p1": "doc1/render_page.v1/page/p1/abc.json"},
        "glossary_ref": "doc1/glossary_payload.v1/document/doc1/gh.json",
        # no search_docs_ref or nav_ref
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
    manifest_ref = "doc1/run_manifest.v1/run/run_1/mh.json"
    _write_artifact(artifact_root, manifest_ref, manifest_data)

    run_data = {"qa_summary_ref": None, "run_manifest_ref": manifest_ref}
    page_refs, companion_refs, _image_refs = _extract_artifact_refs(artifact_root, run_data)

    assert "p1" in page_refs
    assert "glossary_ref" in companion_refs
    assert "search_docs_ref" not in companion_refs
    assert "nav_ref" not in companion_refs

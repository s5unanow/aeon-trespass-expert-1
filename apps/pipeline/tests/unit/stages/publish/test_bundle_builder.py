"""Tests for bundle builder with manifest-driven artifact selection."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.stages.publish.bundle_builder import build_release_bundle


def _write_render_page(artifact_root: Path, doc_id: str, page_id: str) -> str:
    """Write a fake render page artifact and return its ref path."""
    ref_dir = artifact_root / doc_id / "render_page.v1" / "page" / page_id
    ref_dir.mkdir(parents=True, exist_ok=True)
    content = {"page_id": page_id, "blocks": []}
    c_hash = f"hash_{page_id}"
    ref_path = ref_dir / f"{c_hash}.json"
    ref_path.write_text(json.dumps(content), encoding="utf-8")
    return f"{doc_id}/render_page.v1/page/{page_id}/{c_hash}.json"


def test_bundle_uses_explicit_render_refs(tmp_path: Path) -> None:
    """When render_page_refs is provided, only those artifacts are copied."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"

    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    ref_p2 = _write_render_page(artifact_root, "doc1", "p2")
    # Write a third page that should NOT be included
    _write_render_page(artifact_root, "doc1", "p3")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
        render_page_refs={"p1": ref_p1, "p2": ref_p2},
    )

    data_files = [f.path for f in manifest.files]
    assert "data/render_page.p1.json" in data_files
    assert "data/render_page.p2.json" in data_files
    assert "data/render_page.p3.json" not in data_files


def test_bundle_falls_back_to_fs_without_refs(tmp_path: Path) -> None:
    """Without render_page_refs, bundle builder enumerates the filesystem."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"

    _write_render_page(artifact_root, "doc1", "p1")
    _write_render_page(artifact_root, "doc1", "p2")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
    )

    data_files = [f.path for f in manifest.files]
    assert "data/render_page.p1.json" in data_files
    assert "data/render_page.p2.json" in data_files


def test_bundle_copies_exact_content(tmp_path: Path) -> None:
    """Manifest-driven copy preserves exact file content."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"
    ref = _write_render_page(artifact_root, "doc1", "p1")

    build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
        render_page_refs={"p1": ref},
    )

    dest = output_dir / "data" / "render_page.p1.json"
    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["page_id"] == "p1"

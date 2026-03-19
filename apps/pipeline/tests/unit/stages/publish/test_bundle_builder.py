"""Tests for bundle builder with content-addressed, ref-driven bundles."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.stages.publish.bundle_builder import build_release_bundle


def _write_artifact(artifact_root: Path, ref: str, data: dict[str, object]) -> str:
    """Write a fake artifact and return its ref path."""
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return ref


def _write_render_page(artifact_root: Path, doc_id: str, page_id: str) -> str:
    """Write a fake render page artifact and return its ref path."""
    ref = f"{doc_id}/render_page.v1/page/{page_id}/hash_{page_id}.json"
    return _write_artifact(artifact_root, ref, {"page_id": page_id, "blocks": []})


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


def test_bundle_copies_exact_content(tmp_path: Path) -> None:
    """Ref-driven copy preserves exact file content."""
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


def test_build_id_is_content_addressed(tmp_path: Path) -> None:
    """Same input refs produce the same build_id."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    ref_p2 = _write_render_page(artifact_root, "doc1", "p2")
    refs = {"p1": ref_p1, "p2": ref_p2}

    m1 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r1",
        render_page_refs=refs,
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        render_page_refs=refs,
    )

    assert m1.build_id == m2.build_id
    assert m1.content_version == m2.content_version
    assert m1.build_id.startswith("build_")


def test_different_refs_produce_different_build_id(tmp_path: Path) -> None:
    """Different input refs produce different build_ids."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    ref_p2 = _write_render_page(artifact_root, "doc1", "p2")

    m1 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r1",
        render_page_refs={"p1": ref_p1},
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        render_page_refs={"p1": ref_p1, "p2": ref_p2},
    )

    assert m1.build_id != m2.build_id


def test_companion_refs_copied_by_ref(tmp_path: Path) -> None:
    """Companion artifacts are copied using explicit refs, not enumeration."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    glossary_ref = _write_artifact(
        artifact_root,
        "doc1/glossary_payload.v1/document/doc1/gh.json",
        {"entries": []},
    )
    nav_ref = _write_artifact(
        artifact_root,
        "doc1/nav.v1/document/doc1/nh.json",
        {"items": []},
    )

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "release",
        render_page_refs={"p1": ref_p1},
        companion_refs={"glossary_ref": glossary_ref, "nav_ref": nav_ref},
    )

    data_files = [f.path for f in manifest.files]
    assert "data/glossary.json" in data_files
    assert "data/nav.json" in data_files
    assert "data/search_docs.json" not in data_files


def test_companion_refs_affect_build_id(tmp_path: Path) -> None:
    """Companion refs contribute to the content-addressed build_id."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    glossary_ref = _write_artifact(
        artifact_root,
        "doc1/glossary_payload.v1/document/doc1/gh.json",
        {"entries": []},
    )

    m1 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r1",
        render_page_refs={"p1": ref_p1},
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        render_page_refs={"p1": ref_p1},
        companion_refs={"glossary_ref": glossary_ref},
    )

    assert m1.build_id != m2.build_id

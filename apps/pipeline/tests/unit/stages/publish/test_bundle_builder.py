"""Tests for bundle builder with content-addressed, ref-driven bundles."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atr_pipeline.stages.publish.bundle_builder import BundleRefs, build_release_bundle


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
        refs=BundleRefs(render_pages={"p1": ref_p1, "p2": ref_p2}),
    )

    data_files = [f.path for f in manifest.files]
    assert "ru/data/render_page.p1.json" in data_files
    assert "ru/data/render_page.p2.json" in data_files
    assert "ru/data/render_page.p3.json" not in data_files


def test_bundle_copies_exact_content(tmp_path: Path) -> None:
    """Ref-driven copy preserves exact file content."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"
    ref = _write_render_page(artifact_root, "doc1", "p1")

    build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
        refs=BundleRefs(render_pages={"p1": ref}),
    )

    dest = output_dir / "ru" / "data" / "render_page.p1.json"
    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["page_id"] == "p1"


def test_build_id_is_content_addressed(tmp_path: Path) -> None:
    """Same input refs produce the same build_id."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")
    ref_p2 = _write_render_page(artifact_root, "doc1", "p2")
    page_refs = {"p1": ref_p1, "p2": ref_p2}

    m1 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r1",
        refs=BundleRefs(render_pages=page_refs),
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        refs=BundleRefs(render_pages=page_refs),
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
        refs=BundleRefs(render_pages={"p1": ref_p1}),
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        refs=BundleRefs(render_pages={"p1": ref_p1, "p2": ref_p2}),
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
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            companions={"glossary_ref": glossary_ref, "nav_ref": nav_ref},
        ),
    )

    data_files = [f.path for f in manifest.files]
    assert "ru/data/glossary.json" in data_files
    assert "ru/data/nav.json" in data_files
    assert "ru/data/search_docs.json" not in data_files


def test_image_refs_copied_to_bundle(tmp_path: Path) -> None:
    """Image assets are copied into data/images/ with correct filenames."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    # Write fake image files
    img_path = artifact_root / "doc1/image/page/img0000/abc123.png"
    img_path.parent.mkdir(parents=True, exist_ok=True)
    img_path.write_bytes(b"\x89PNG fake image data")

    img2_path = artifact_root / "doc1/image/page/img0001/def456.jpeg"
    img2_path.parent.mkdir(parents=True, exist_ok=True)
    img2_path.write_bytes(b"\xff\xd8 fake jpeg data")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            images={
                "img0000": "doc1/image/page/img0000/abc123.png",
                "img0001": "doc1/image/page/img0001/def456.jpeg",
            },
        ),
    )

    data_files = [f.path for f in manifest.files]
    assert "images/img0000.png" in data_files
    assert "images/img0001.jpeg" in data_files

    # Verify files actually exist in the bundle (images are shared, not edition-scoped)
    assert (output_dir / "images" / "img0000.png").exists()
    assert (output_dir / "images" / "img0001.jpeg").exists()


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
        refs=BundleRefs(render_pages={"p1": ref_p1}),
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            companions={"glossary_ref": glossary_ref},
        ),
    )

    assert m1.build_id != m2.build_id


def test_raster_refs_copied_to_bundle(tmp_path: Path) -> None:
    """Raster assets are copied into rasters/ dir in release bundle."""
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "release"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    raster_path = artifact_root / "doc1/raster/page/p0007__150dpi/abc123.png"
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    raster_path.write_bytes(b"\x89PNG fake raster")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=output_dir,
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            rasters={"p0007__150dpi": "doc1/raster/page/p0007__150dpi/abc123.png"},
        ),
    )

    data_files = [f.path for f in manifest.files]
    assert "rasters/p0007__150dpi.png" in data_files
    assert (output_dir / "rasters" / "p0007__150dpi.png").exists()


def test_manifest_written_atomically(tmp_path: Path) -> None:
    """S5U-625: manifest.json must be written via atomic_write_text.

    This verifies the fix routes the manifest write through
    ``atr_pipeline.store.atomic_write.atomic_write_text`` rather than plain
    ``Path.write_text``. Without the fix, the patched helper is never called
    and the assertion fails.
    """
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    with patch("atr_pipeline.stages.publish.bundle_builder.atomic_write_text") as mock_atomic:
        build_release_bundle(
            document_id="doc1",
            artifact_root=artifact_root,
            output_dir=tmp_path / "release",
            refs=BundleRefs(render_pages={"p1": ref_p1}),
        )

    # atomic_write_text must be invoked once for the manifest
    assert mock_atomic.call_count == 1, (
        f"Expected manifest write to route through atomic_write_text, "
        f"but it was called {mock_atomic.call_count} times"
    )
    call_args = mock_atomic.call_args
    manifest_path = call_args.args[0]
    manifest_body = call_args.args[1]
    assert manifest_path.name == "manifest.json"
    # Body is valid JSON with content-addressed build_id
    parsed = json.loads(manifest_body)
    assert parsed["document_id"] == "doc1"
    assert parsed["build_id"].startswith("build_")


def test_draft_label_stamped_into_manifest(tmp_path: Path) -> None:
    """S5U-894: draft-label refs flow into the on-disk BuildManifestV1.

    Red-before: at 7f7a251 BundleRefs has no draft fields and BuildManifestV1
    has no draft fields, so these refs cannot be passed and the manifest cannot
    carry the label.
    """
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "release",
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            review_only_draft=True,
            blocking_qa_codes=["GLUED_TEXT", "DEAD_PAGE_REF"],
            review_pack_ref="doc1/review_pack.v1/document/doc1/rp.json",
        ),
    )

    assert manifest.review_only_draft is True
    assert manifest.blocking_qa_codes == ["GLUED_TEXT", "DEAD_PAGE_REF"]
    assert manifest.review_pack_ref == "doc1/review_pack.v1/document/doc1/rp.json"

    # Persisted to disk, not just the in-memory object.
    on_disk = json.loads((tmp_path / "release" / "ru" / "manifest.json").read_text())
    assert on_disk["review_only_draft"] is True
    assert on_disk["review_pack_ref"] == "doc1/review_pack.v1/document/doc1/rp.json"


def test_clean_bundle_has_no_draft_label(tmp_path: Path) -> None:
    """S5U-894: a clean (non-draft) build leaves the label at its defaults."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    manifest = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "release",
        refs=BundleRefs(render_pages={"p1": ref_p1}),
    )

    assert manifest.review_only_draft is False
    assert manifest.blocking_qa_codes == []
    assert manifest.review_pack_ref == ""


def test_draft_label_does_not_change_build_id(tmp_path: Path) -> None:
    """S5U-894: the draft label is metadata, not content — build_id is unchanged.

    A draft and a clean build of the SAME artifacts must share build identity;
    only their loud on-disk label differs.
    """
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    clean = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "clean",
        refs=BundleRefs(render_pages={"p1": ref_p1}),
    )
    draft = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "draft",
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            review_only_draft=True,
            blocking_qa_codes=["GLUED_TEXT"],
            review_pack_ref="doc1/review_pack.v1/document/doc1/rp.json",
        ),
    )

    assert clean.build_id == draft.build_id
    assert clean.content_version == draft.content_version


def test_raster_refs_affect_build_id(tmp_path: Path) -> None:
    """Raster refs contribute to content-addressed build_id."""
    artifact_root = tmp_path / "artifacts"
    ref_p1 = _write_render_page(artifact_root, "doc1", "p1")

    raster_path = artifact_root / "doc1/raster/page/p0007__150dpi/abc.png"
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    raster_path.write_bytes(b"\x89PNG")

    m1 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r1",
        refs=BundleRefs(render_pages={"p1": ref_p1}),
    )
    m2 = build_release_bundle(
        document_id="doc1",
        artifact_root=artifact_root,
        output_dir=tmp_path / "r2",
        refs=BundleRefs(
            render_pages={"p1": ref_p1},
            rasters={"p0007__150dpi": "doc1/raster/page/p0007__150dpi/abc.png"},
        ),
    )

    assert m1.build_id != m2.build_id

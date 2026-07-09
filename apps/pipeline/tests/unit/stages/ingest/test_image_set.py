"""Tests for image-set ingest: registration, determinism, cache, and refusals (S5U-1536)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig
from atr_pipeline.config.source import ImageSetSource
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.image_set import (
    ImageSetError,
    _resolve_within_root,
    ingest_image_set,
    validate_image_set,
)
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1

DOC = "ts"


# --- helpers ---------------------------------------------------------------


def _png(
    path: Path, *, color: tuple[int, int, int] = (10, 20, 30), size: tuple[int, int] = (8, 8)
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _manifest_toml(entries: list[tuple[str, str, int]], *, document_id: str = DOC) -> str:
    lines = ['schema_version = "image_set_manifest.v1"', f'document_id = "{document_id}"', ""]
    for image_id, path, page in entries:
        lines += [
            "[[images]]",
            f'image_id = "{image_id}"',
            f'path = "{path}"',
            f"page_number = {page}",
            "",
        ]
    return "\n".join(lines)


def _standard_root(root: Path) -> Path:
    """Write a valid 3-image / 2-page image set under ``root`` and return the manifest path."""
    _png(root / "images" / "a.png", color=(200, 0, 0))
    _png(root / "images" / "b.png", color=(0, 200, 0))
    _png(root / "images" / "c.png", color=(0, 0, 200), size=(8, 12))
    manifest = root / "manifest.toml"
    manifest.write_text(
        _manifest_toml(
            [
                ("page_01_a", "images/a.png", 1),
                ("page_01_b", "images/b.png", 1),
                ("page_02_a", "images/c.png", 2),
            ]
        )
    )
    return manifest


def _files(store: ArtifactStore) -> list[Path]:
    return [p for p in store.root.rglob("*") if p.is_file()]


def _make_ctx(root: Path) -> StageContext:
    store = ArtifactStore(root / "artifacts")
    conn = open_registry(root / "registry.db")
    start_run(conn, run_id="r", document_id=DOC, pipeline_version="0.1.0", config_hash="t")
    cfg = DocumentBuildConfig(
        document=DocumentConfig(id=DOC, source=ImageSetSource(manifest="manifest.toml")),
        repo_root=root,
        artifact_root=root / "artifacts",
    )
    return StageContext(
        run_id="r",
        document_id=DOC,
        config=cfg,
        artifact_store=store,
        registry_conn=conn,
        repo_root=root,
    )


# --- happy path ------------------------------------------------------------


def test_ingest_image_set_registers_artifacts_and_manifest(tmp_path: Path) -> None:
    manifest = _standard_root(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    result = ingest_image_set(
        store=store,
        document_id=DOC,
        manifest_path=manifest,
        repo_root=tmp_path,
        logger=logging.getLogger("t"),
    )
    assert result.source_kind == "image_set"
    assert result.source_pdf_sha256 == ""
    assert len(result.source_image_set_sha256) == 64
    assert result.page_count == 2
    assert [p.page_id for p in result.pages] == ["p0001", "p0002"]
    assert [img.image_id for img in result.images] == ["page_01_a", "page_01_b", "page_02_a"]
    for img in result.images:
        assert len(img.sha256) == 64
        assert img.media_type == "image/png"
        # Every registered image is on disk at its content-addressed ref.
        assert (store.root / img.artifact_ref).is_file()


def test_ingest_image_set_via_execute_stage(tmp_path: Path) -> None:
    _standard_root(tmp_path)
    ctx = _make_ctx(tmp_path)
    result = execute_stage(IngestStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    assert manifest.source_kind == "image_set"
    assert len(manifest.images) == 3
    # Raw image artifacts registered under the source_image family.
    assert (tmp_path / "artifacts" / DOC / "source_image" / "page" / "page_01_a").is_dir()


def test_ingest_image_set_manifest_is_byte_identical_across_runs(tmp_path: Path) -> None:
    manifest = _standard_root(tmp_path)

    def run_once(subdir: str) -> str:
        store = ArtifactStore(tmp_path / subdir)
        m = ingest_image_set(
            store=store,
            document_id=DOC,
            manifest_path=manifest,
            repo_root=tmp_path,
            logger=logging.getLogger("t"),
        )
        return m.model_dump_json(indent=2)

    assert run_once("run1") == run_once("run2")


# --- cache key incorporates image identity (criterion 6) -------------------


def test_extra_cache_inputs_changes_when_image_byte_changes(tmp_path: Path) -> None:
    _standard_root(tmp_path)
    ctx = _make_ctx(tmp_path)
    stage = IngestStage()
    before = stage.extra_cache_inputs(ctx)
    assert before[0].startswith("image_set_sha256:")
    # Re-hash identical inputs → identical key.
    assert stage.extra_cache_inputs(ctx) == before
    # Mutate one image's bytes → key changes.
    _png(tmp_path / "images" / "a.png", color=(1, 2, 3))
    after = stage.extra_cache_inputs(ctx)
    assert after != before


def test_extra_cache_inputs_unresolved_sentinel_on_missing_manifest(tmp_path: Path) -> None:
    # No manifest written at all → sentinel, run() remains the authoritative failure.
    ctx = _make_ctx(tmp_path)
    assert IngestStage().extra_cache_inputs(ctx) == ["image_set_sha256:unresolved"]


def test_execute_stage_cache_hit_on_identical_rerun(tmp_path: Path) -> None:
    _standard_root(tmp_path)
    ctx = _make_ctx(tmp_path)
    r1 = execute_stage(IngestStage(), ctx)
    r2 = execute_stage(IngestStage(), ctx)
    assert r1.success and not r1.cached
    assert r2.success and r2.cached
    assert r1.cache_key == r2.cache_key
    # Cache hit short-circuits run(), but the registered raw images remain on disk.
    assert (tmp_path / "artifacts" / DOC / "source_image" / "page" / "page_01_a").is_dir()


def test_execute_stage_cache_miss_when_image_byte_changes(tmp_path: Path) -> None:
    _standard_root(tmp_path)
    ctx = _make_ctx(tmp_path)
    r1 = execute_stage(IngestStage(), ctx)
    _png(tmp_path / "images" / "a.png", color=(9, 9, 9))
    r2 = execute_stage(IngestStage(), ctx)
    assert not r1.cached
    assert r2.success and not r2.cached
    assert r1.cache_key != r2.cache_key


# --- refusals (criterion 5): each raises + leaves the store untouched -------


def _assert_refused(tmp_path: Path, manifest: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ImageSetError):
        ingest_image_set(
            store=store,
            document_id=DOC,
            manifest_path=manifest,
            repo_root=tmp_path,
            logger=logging.getLogger("t"),
        )
    assert _files(store) == [], "refused ingest must not write any artifact"


def test_refuse_path_traversal(tmp_path: Path) -> None:
    _png(tmp_path.parent / "escape.png")  # a real image, but outside the root
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "../escape.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_absolute_path_escape(tmp_path: Path) -> None:
    outside = _png(tmp_path.parent / "abs.png")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", str(outside), 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_symlink_escape(tmp_path: Path) -> None:
    target = _png(tmp_path.parent / "sym_target.png")
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    link = tmp_path / "images" / "link.png"
    link.symlink_to(target)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/link.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_unsupported_media_type_text_as_png(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / "fake.png").write_text("this is not an image")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/fake.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_unsupported_media_type_gif(tmp_path: Path) -> None:
    gif = tmp_path / "images" / "a.gif"
    gif.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (1, 1, 1)).save(gif, format="GIF")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/a.gif", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_decompression_bomb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A modest PNG exceeds an artificially tiny pixel limit → Pillow raises
    # DecompressionBombError, which must surface as a clean ImageSetError refusal.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    _png(tmp_path / "images" / "a.png", size=(64, 64))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/a.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_duplicate_image_id(tmp_path: Path) -> None:
    _png(tmp_path / "images" / "a.png")
    _png(tmp_path / "images" / "b.png", color=(1, 1, 1))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("dup", "images/a.png", 1), ("dup", "images/b.png", 2)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_duplicate_manifest_entry(tmp_path: Path) -> None:
    _png(tmp_path / "images" / "a.png")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/a.png", 1), ("y", "images/a.png", 2)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_missing_image(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/nope.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_malformed_manifest_toml(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("this is = = not valid toml [[[")
    _assert_refused(tmp_path, manifest)


def test_refuse_invalid_manifest_schema(tmp_path: Path) -> None:
    _png(tmp_path / "images" / "a.png")
    manifest = tmp_path / "manifest.toml"
    # image_id violates the filesystem-safe pattern → schema validation error.
    manifest.write_text(_manifest_toml([("../evil", "images/a.png", 1)]))
    _assert_refused(tmp_path, manifest)


def test_refuse_manifest_document_id_mismatch(tmp_path: Path) -> None:
    _png(tmp_path / "images" / "a.png")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("x", "images/a.png", 1)], document_id="other"))
    _assert_refused(tmp_path, manifest)


def test_refuse_missing_manifest(tmp_path: Path) -> None:
    _assert_refused(tmp_path, tmp_path / "does_not_exist.toml")


# --- path-safety primitive -------------------------------------------------


def test_resolve_within_root_rejects_null_byte(tmp_path: Path) -> None:
    with pytest.raises(ImageSetError, match="null byte"):
        _resolve_within_root(
            "images/pa\x00ge.png", base_dir=tmp_path, repo_root=tmp_path, label="image path"
        )


def test_resolve_within_root_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ImageSetError, match="outside the allowed root"):
        _resolve_within_root(
            "../../etc/passwd", base_dir=tmp_path, repo_root=tmp_path, label="image path"
        )


def test_resolve_within_root_allows_path_under_root(tmp_path: Path) -> None:
    resolved = _resolve_within_root(
        "images/a.png", base_dir=tmp_path, repo_root=tmp_path, label="image path"
    )
    assert resolved == Path(os.path.realpath(tmp_path / "images" / "a.png"))


def test_validate_image_set_returns_sorted_images(tmp_path: Path) -> None:
    # Author out of order; validate must return sorted by (page_number, image_id).
    _png(tmp_path / "images" / "a.png")
    _png(tmp_path / "images" / "b.png", color=(1, 1, 1))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(_manifest_toml([("z2", "images/b.png", 2), ("z1", "images/a.png", 1)]))
    validated = validate_image_set(manifest, repo_root=tmp_path, document_id=DOC)
    assert [ri.entry.image_id for ri in validated.images] == ["z1", "z2"]


# Symlink creation is unavailable on some CI shells; skip cleanly if so.
if sys.platform == "win32":  # pragma: no cover - repo is darwin/linux only
    del test_refuse_symlink_escape

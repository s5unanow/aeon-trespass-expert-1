"""Image-set ingest tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import sha256_bytes
from atr_schemas.source_manifest_v1 import SourceManifestV1

PNG_ONE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01"
    b"\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_TWO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
    b"\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_manifest(root: Path, entries: list[dict[str, Any]]) -> Path:
    manifest_path = root / "source" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "source_kind": "image_set",
                "images": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_image(root: Path, rel_path: str, data: bytes) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _entry(
    *,
    image_id: str | None = None,
    page_number: int = 1,
    path: str = "page-001.png",
    sha256: str | None = None,
    media_type: str = "image/png",
) -> dict[str, Any]:
    image_sha = sha256 or sha256_bytes(PNG_ONE)
    page_id = f"p{page_number:04d}"
    return {
        "image_id": image_id or f"img.{page_id}.{image_sha[:12]}",
        "page_id": page_id,
        "page_number": page_number,
        "path": path,
        "media_type": media_type,
        "sha256": image_sha,
        "capture": {"device": "unit-test"},
        "exif": {"DateTimeOriginal": "2026:07:09 10:00:00"},
    }


def _ctx(
    tmp_path: Path,
    manifest_path: Path,
    *,
    doc_id: str = "image_doc",
    run_id: str | None = None,
) -> StageContext:
    resolved_run_id = run_id or f"run_{doc_id}"
    config = DocumentBuildConfig(
        document=DocumentConfig.model_validate(
            {
                "id": doc_id,
                "source_kind": "image_set",
                "image_set_manifest": str(manifest_path.relative_to(tmp_path)),
            }
        ),
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
    )
    store = ArtifactStore(config.artifact_root)
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id=resolved_run_id,
        document_id=doc_id,
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id=resolved_run_id,
        document_id=doc_id,
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=tmp_path,
    )


def _manifest_from_result(ctx: StageContext) -> SourceManifestV1:
    result = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])
    assert result.success, result.error
    assert result.artifact_ref is not None
    return SourceManifestV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))


def test_image_set_ingest_writes_raw_images_and_deterministic_manifest(tmp_path: Path) -> None:
    _write_image(tmp_path, "source/page-001.png", PNG_ONE)
    manifest_path = _write_manifest(tmp_path, [_entry()])

    ctx1 = _ctx(tmp_path, manifest_path)
    manifest1 = _manifest_from_result(ctx1)
    manifest_json1 = manifest1.model_dump_json()

    ctx2 = _ctx(tmp_path, manifest_path, doc_id="image_doc", run_id="run_image_doc_2")
    manifest2 = _manifest_from_result(ctx2)

    assert manifest1.source_kind == "image_set"
    assert manifest1.source_pdf_sha256 == ""
    assert len(manifest1.source_image_set_sha256) == 64
    assert len(manifest1.source_image_set_manifest_sha256) == 64
    assert manifest1.page_count == 1
    assert manifest1.pages[0].source_image_id == f"img.p0001.{sha256_bytes(PNG_ONE)[:12]}"
    assert manifest1.image_set is not None
    assert manifest1.image_set.images[0].sha256 == sha256_bytes(PNG_ONE)
    assert list((tmp_path / "artifacts" / "image_doc" / "raw_image" / "page").glob("*/*.png"))
    assert list(
        (tmp_path / "artifacts" / "image_doc" / "raw_image_metadata.v1" / "page").glob("*/*.json")
    )
    assert manifest2.model_dump_json() == manifest_json1


@pytest.mark.parametrize(
    ("case_name", "entries", "images"),
    [
        ("traversal", [_entry(path="../escape.png")], {"escape.png": PNG_ONE}),
        ("absolute_escape", [], {}),
        ("null_byte", [_entry(path="source/page-001.png\x00")], {"source/page-001.png": PNG_ONE}),
        (
            "unsupported_media",
            [_entry(path="page-001.gif", media_type="image/gif")],
            {"source/page-001.gif": b"GIF89a"},
        ),
        (
            "duplicate_id",
            [_entry(), _entry(image_id=f"img.p0001.{sha256_bytes(PNG_ONE)[:12]}", page_number=2)],
            {"source/page-001.png": PNG_ONE},
        ),
        (
            "duplicate_entry",
            [_entry(), _entry(page_number=2, path="page-001.png")],
            {"source/page-001.png": PNG_ONE},
        ),
        ("missing_image", [_entry(path="missing.png")], {}),
    ],
)
def test_image_set_ingest_refuses_invalid_input_without_artifact_writes(
    tmp_path: Path,
    case_name: str,
    entries: list[dict[str, Any]],
    images: dict[str, bytes],
) -> None:
    if case_name == "absolute_escape":
        outside = tmp_path.parent / f"{tmp_path.name}_outside.png"
        outside.write_bytes(PNG_ONE)
        entries = [_entry(path=str(outside))]
    for rel_path, data in images.items():
        _write_image(tmp_path, rel_path, data)
    manifest_path = _write_manifest(tmp_path, entries)

    ctx = _ctx(tmp_path, manifest_path)
    result = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])

    assert not result.success
    assert not (tmp_path / "artifacts" / "image_doc").exists()


def test_image_set_ingest_refuses_malformed_manifest_without_artifact_writes(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "source" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{not-json", encoding="utf-8")

    ctx = _ctx(tmp_path, manifest_path)
    result = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])

    assert not result.success
    assert not (tmp_path / "artifacts" / "image_doc").exists()


def test_image_set_extra_cache_inputs_track_image_bytes(tmp_path: Path) -> None:
    image_rel = "source/page-001.png"
    manifest_rel = "page-001.png"
    _write_image(tmp_path, image_rel, PNG_ONE)
    manifest_path = _write_manifest(
        tmp_path,
        [_entry(path=manifest_rel, sha256=sha256_bytes(PNG_ONE))],
    )
    stage = IngestStage()

    first = stage.extra_cache_inputs(_ctx(tmp_path, manifest_path, doc_id="image_doc_a"))
    first_again = stage.extra_cache_inputs(_ctx(tmp_path, manifest_path, doc_id="image_doc_b"))

    _write_image(tmp_path, image_rel, PNG_TWO)
    _write_manifest(tmp_path, [_entry(path=manifest_rel, sha256=sha256_bytes(PNG_TWO))])
    second = stage.extra_cache_inputs(_ctx(tmp_path, manifest_path, doc_id="image_doc_c"))

    assert first == first_again
    assert first != second
    assert first[0].startswith("image_set_sha256:")


def test_image_set_ingest_cache_hit_on_identical_inputs(tmp_path: Path) -> None:
    _write_image(tmp_path, "source/page-001.png", PNG_ONE)
    manifest_path = _write_manifest(tmp_path, [_entry()])
    ctx = _ctx(tmp_path, manifest_path)

    r1 = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])
    r2 = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])

    assert r1.success and not r1.cached
    assert r2.success and r2.cached

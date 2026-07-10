"""Image-set ingest artifact, refusal, determinism, and cache contracts."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _png_bytes(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(output, format="PNG")
    return output.getvalue()


def _entry(filename: str, data: bytes, page_number: int) -> dict[str, object]:
    return {
        "image_id": f"img.page-{page_number:04d}",
        "path": filename,
        "media_type": "image/png",
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_id": f"p{page_number:04d}",
        "page_number": page_number,
    }


def _write_valid_source(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    first = _png_bytes("red")
    second = _png_bytes("blue")
    (source_dir / "page_0001.png").write_bytes(first)
    (source_dir / "page_0002.png").write_bytes(second)
    manifest = source_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "images": [
                    _entry("page_0001.png", first, 1),
                    _entry("page_0002.png", second, 2),
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _make_ctx(root: Path, *, run_id: str = "image_set_run") -> StageContext:
    manifest = root / "source" / "manifest.json"
    config = DocumentBuildConfig(
        document=DocumentConfig.model_validate(
            {
                "id": "photos",
                "source_kind": "image_set",
                "source_manifest": str(manifest),
            }
        ),
        repo_root=root,
        artifact_root=root / "artifacts",
    )
    store = ArtifactStore(config.artifact_root)
    conn = open_registry(root / "registry.db")
    start_run(
        conn,
        run_id=run_id,
        document_id="photos",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id=run_id,
        document_id="photos",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=root,
    )


def _load_manifest(ctx: StageContext, result_ref: object) -> SourceManifestV1:
    assert result_ref is not None
    return SourceManifestV1.model_validate(ctx.artifact_store.get_json(result_ref))  # type: ignore[arg-type]


def test_image_set_ingest_registers_raw_images_and_source_manifest(tmp_path: Path) -> None:
    _write_valid_source(tmp_path)
    ctx = _make_ctx(tmp_path)

    result = execute_stage(IngestStage(), ctx)

    assert result.success and not result.cached
    manifest = _load_manifest(ctx, result.artifact_ref)
    assert manifest.source_kind == "image_set"
    assert manifest.source_pdf_sha256 == ""
    assert manifest.page_count == 2
    assert len(manifest.source_manifest_sha256) == 64
    assert len(manifest.source_image_set_sha256) == 64
    assert [entry.image_id for entry in manifest.source_images] == [
        "img.page-0001",
        "img.page-0002",
    ]
    for entry in manifest.source_images:
        raw_path = ctx.artifact_store.root / entry.raw_artifact_ref
        assert raw_path.is_file()
        assert raw_path.read_bytes()


def test_image_set_manifest_json_is_identical_across_fresh_runs(tmp_path: Path) -> None:
    source_root = tmp_path / "source_root"
    manifest_path = _write_valid_source(source_root)
    outputs: list[bytes] = []
    for name in ("first", "second"):
        run_root = tmp_path / name
        run_root.mkdir()
        ctx = _make_ctx(run_root, run_id=f"run_{name}")
        ctx.config.repo_root = tmp_path
        ctx.repo_root = tmp_path
        ctx.config.document.source_manifest = str(manifest_path)
        ctx.config.document.source.manifest_path = str(manifest_path)  # type: ignore[union-attr]
        result = execute_stage(IngestStage(), ctx)
        assert result.success
        assert result.artifact_ref is not None
        outputs.append(ctx.artifact_store.get_path(result.artifact_ref).read_bytes())

    assert outputs[0] == outputs[1]


def test_image_set_cache_hits_then_invalidates_on_changed_image_bytes(tmp_path: Path) -> None:
    manifest_path = _write_valid_source(tmp_path)
    ctx = _make_ctx(tmp_path)

    first = execute_stage(IngestStage(), ctx)
    identical = execute_stage(IngestStage(), ctx)

    replacement = _png_bytes("green")
    (manifest_path.parent / "page_0001.png").write_bytes(replacement)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["images"][0]["sha256"] = hashlib.sha256(replacement).hexdigest()
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    changed = execute_stage(IngestStage(), ctx)

    assert first.success and not first.cached
    assert identical.success and identical.cached
    assert changed.success and not changed.cached
    assert first.cache_key == identical.cache_key
    assert changed.cache_key != first.cache_key


def test_image_set_cache_repairs_missing_raw_artifact(tmp_path: Path) -> None:
    _write_valid_source(tmp_path)
    ctx = _make_ctx(tmp_path)
    first = execute_stage(IngestStage(), ctx)
    manifest = _load_manifest(ctx, first.artifact_ref)
    missing_raw = ctx.artifact_store.root / manifest.source_images[0].raw_artifact_ref
    missing_raw.unlink()

    repaired = execute_stage(IngestStage(), ctx)

    assert repaired.success and not repaired.cached
    assert missing_raw.is_file()


@pytest.mark.parametrize(
    "case",
    [
        "traversal",
        "absolute_escape",
        "null_byte",
        "unsupported_media",
        "duplicate_id",
        "duplicate_path",
        "malformed_manifest",
        "missing_image",
    ],
)
def test_image_set_refusals_leave_artifact_store_untouched(
    tmp_path: Path,
    case: str,
) -> None:
    manifest_path = _write_valid_source(tmp_path)
    if case == "malformed_manifest":
        manifest_path.write_text("{not json", encoding="utf-8")
    else:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        first = payload["images"][0]
        second = payload["images"][1]
        if case == "traversal":
            first["path"] = "../page_0001.png"
        elif case == "absolute_escape":
            outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
            outside.write_bytes(_png_bytes("black"))
            first["path"] = str(outside)
        elif case == "null_byte":
            first["path"] = "page_0001.png\x00"
        elif case == "unsupported_media":
            first["media_type"] = "image/gif"
        elif case == "duplicate_id":
            second["image_id"] = first["image_id"]
        elif case == "duplicate_path":
            second["path"] = first["path"]
        elif case == "missing_image":
            first["path"] = "missing.png"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    ctx = _make_ctx(tmp_path)
    result = execute_stage(IngestStage(), ctx)

    assert not result.success
    assert list(ctx.artifact_store.root.rglob("*")) == []

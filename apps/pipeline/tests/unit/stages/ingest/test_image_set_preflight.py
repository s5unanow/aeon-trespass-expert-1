"""Fail-closed preflight tests for photographed-page sources."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from atr_pipeline.stages.ingest.image_set_preflight import preflight_image_set
from atr_pipeline.stages.ingest.path_safety import resolve_allowed_path


def _image_bytes(image_format: str = "PNG", color: str = "red") -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(output, format=image_format)
    return output.getvalue()


def _entry(path: str, data: bytes, *, page_number: int = 1) -> dict[str, object]:
    extension = Path(path).suffix.lower()
    return {
        "image_id": f"img.page-{page_number:04d}",
        "path": path,
        "media_type": "image/jpeg" if extension in {".jpg", ".jpeg"} else "image/png",
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_id": f"p{page_number:04d}",
        "page_number": page_number,
    }


def _write_manifest(root: Path, images: list[dict[str, object]]) -> Path:
    path = root / "source" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"images": images}), encoding="utf-8")
    return path


def _valid_source(root: Path) -> tuple[Path, bytes, bytes]:
    source_dir = root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    first = _image_bytes(color="red")
    second = _image_bytes(color="blue")
    (source_dir / "page_0001.png").write_bytes(first)
    (source_dir / "page_0002.png").write_bytes(second)
    manifest = _write_manifest(
        root,
        [
            _entry("page_0001.png", first),
            _entry("page_0002.png", second, page_number=2),
        ],
    )
    return manifest, first, second


def test_preflight_returns_ordered_validated_image_plan(tmp_path: Path) -> None:
    manifest_path, first, second = _valid_source(tmp_path)

    plan = preflight_image_set(
        str(manifest_path),
        base_dir=tmp_path,
        allowed_roots=(tmp_path,),
    )

    assert plan.manifest_path == manifest_path.resolve()
    assert len(plan.manifest_sha256) == 64
    assert len(plan.image_set_sha256) == 64
    assert [image.entry.page_id for image in plan.images] == ["p0001", "p0002"]
    assert [image.data for image in plan.images] == [first, second]
    assert plan.images[0].raw_image_id.startswith("raw.p0001.")


def test_resolve_allowed_path_rejects_traversal_before_resolution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="traversal"):
        resolve_allowed_path(
            "../manifest.json",
            base_dir=tmp_path,
            allowed_roots=(tmp_path,),
            label="image-set manifest",
        )


def test_resolve_allowed_path_rejects_absolute_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-manifest.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside allowed roots"):
        resolve_allowed_path(
            str(outside),
            base_dir=tmp_path,
            allowed_roots=(tmp_path,),
            label="image-set manifest",
        )


def test_resolve_allowed_path_rejects_null_byte(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="null byte"):
        resolve_allowed_path(
            "manifest.json\x00.png",
            base_dir=tmp_path,
            allowed_roots=(tmp_path,),
            label="image-set manifest",
        )


def test_preflight_rejects_symlink_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    data = _image_bytes()
    outside_image = outside / "page.png"
    outside_image.write_bytes(data)
    (allowed / "escaped.png").symlink_to(outside_image)
    manifest = _write_manifest(allowed, [_entry("../escaped.png", data)])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["images"][0]["path"] = str(allowed / "escaped.png")
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="outside allowed roots"):
        preflight_image_set(
            str(manifest),
            base_dir=allowed,
            allowed_roots=(allowed,),
        )


def test_preflight_rejects_unsupported_media_type(tmp_path: Path) -> None:
    data = _image_bytes()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "page.png").write_bytes(data)
    entry = _entry("page.png", data)
    entry["media_type"] = "image/gif"
    manifest = _write_manifest(tmp_path, [entry])

    with pytest.raises(ValidationError, match="media_type"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


@pytest.mark.parametrize(
    ("duplicate_field", "message"),
    [
        ("image_id", "duplicate image_id"),
        ("path", "duplicate image path"),
    ],
)
def test_preflight_rejects_duplicate_manifest_entries(
    tmp_path: Path,
    duplicate_field: str,
    message: str,
) -> None:
    manifest, _, _ = _valid_source(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["images"][1][duplicate_field] = payload["images"][0][duplicate_field]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match=message):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_duplicate_resolved_paths(tmp_path: Path) -> None:
    manifest, _, _ = _valid_source(tmp_path)
    alias = manifest.parent / "alias.png"
    alias.symlink_to(manifest.parent / "page_0001.png")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["images"][1]["path"] = "alias.png"
    payload["images"][1]["sha256"] = payload["images"][0]["sha256"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate resolved image path"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_malformed_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValidationError, match="Invalid JSON"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_missing_image(tmp_path: Path) -> None:
    data = _image_bytes()
    manifest = _write_manifest(tmp_path, [_entry("missing.png", data)])

    with pytest.raises(FileNotFoundError, match="image-set image not found"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_sha256_mismatch(tmp_path: Path) -> None:
    manifest, _, _ = _valid_source(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["images"][0]["sha256"] = "f" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="sha256 mismatch"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_declared_media_mismatch(tmp_path: Path) -> None:
    manifest, _, _ = _valid_source(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["images"][0]["media_type"] = "image/jpeg"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match detected"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))


def test_preflight_rejects_corrupt_image_bytes(tmp_path: Path) -> None:
    data = b"not an image"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "page.png").write_bytes(data)
    manifest = _write_manifest(tmp_path, [_entry("page.png", data)])

    with pytest.raises(ValueError, match="invalid image bytes"):
        preflight_image_set(str(manifest), base_dir=tmp_path, allowed_roots=(tmp_path,))

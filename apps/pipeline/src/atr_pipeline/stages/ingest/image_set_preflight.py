"""Read and validate a complete image-set source before artifact writes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from atr_pipeline.stages.ingest.path_safety import resolve_allowed_path
from atr_pipeline.utils.hashing import sha256_bytes, sha256_str
from atr_schemas.image_set_manifest_v1 import (
    CaptureMetadataV1,
    ImageMediaType,
    ImageSetImageEntryV1,
    ImageSetManifestV1,
)

_FORMAT_TO_MEDIA: dict[str, ImageMediaType] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}
_MEDIA_TO_EXTENSION: dict[ImageMediaType, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


@dataclass(frozen=True)
class PreparedImage:
    """One fully validated image ready for immutable registration."""

    entry: ImageSetImageEntryV1
    path: Path
    data: bytes
    media_type: ImageMediaType
    extension: str
    raw_image_id: str
    capture: CaptureMetadataV1


@dataclass(frozen=True)
class ImageSetIngestPlan:
    """Side-effect-free result of validating an entire image set."""

    manifest_path: Path
    manifest_sha256: str
    image_set_sha256: str
    images: tuple[PreparedImage, ...]


def preflight_image_set(
    manifest_path: str,
    *,
    base_dir: Path,
    allowed_roots: tuple[Path, ...],
) -> ImageSetIngestPlan:
    """Validate manifest, paths, bytes, hashes, media, and ordered identity."""
    resolved_manifest = resolve_allowed_path(
        manifest_path,
        base_dir=base_dir,
        allowed_roots=allowed_roots,
        label="image-set manifest",
    )
    manifest_bytes = resolved_manifest.read_bytes()
    manifest = ImageSetManifestV1.model_validate_json(manifest_bytes)

    prepared: list[PreparedImage] = []
    resolved_paths: set[Path] = set()
    for entry in manifest.images:
        resolved_image = resolve_allowed_path(
            entry.path,
            base_dir=resolved_manifest.parent,
            allowed_roots=allowed_roots,
            label="image-set image",
        )
        if resolved_image in resolved_paths:
            msg = f"duplicate resolved image path: {resolved_image}"
            raise ValueError(msg)
        resolved_paths.add(resolved_image)

        data = resolved_image.read_bytes()
        actual_sha256 = sha256_bytes(data)
        if actual_sha256 != entry.sha256:
            msg = (
                f"sha256 mismatch for {entry.image_id}: "
                f"manifest={entry.sha256}, actual={actual_sha256}"
            )
            raise ValueError(msg)

        detected_media, capture = _inspect_image(data, entry.capture, entry.image_id)
        if detected_media != entry.media_type:
            msg = (
                f"declared media_type {entry.media_type!r} does not match detected "
                f"{detected_media!r} for {entry.image_id}"
            )
            raise ValueError(msg)
        prepared.append(
            PreparedImage(
                entry=entry,
                path=resolved_image,
                data=data,
                media_type=detected_media,
                extension=_MEDIA_TO_EXTENSION[detected_media],
                raw_image_id=f"raw.{entry.page_id}.{actual_sha256[:12]}",
                capture=capture,
            )
        )

    identity = [
        {
            "image_id": image.entry.image_id,
            "page_id": image.entry.page_id,
            "page_number": image.entry.page_number,
            "media_type": image.media_type,
            "sha256": image.entry.sha256,
        }
        for image in prepared
    ]
    canonical_identity = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return ImageSetIngestPlan(
        manifest_path=resolved_manifest,
        manifest_sha256=sha256_bytes(manifest_bytes),
        image_set_sha256=sha256_str(canonical_identity),
        images=tuple(prepared),
    )


def _inspect_image(
    data: bytes,
    declared: CaptureMetadataV1,
    image_id: str,
) -> tuple[ImageMediaType, CaptureMetadataV1]:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            if image_format not in _FORMAT_TO_MEDIA:
                msg = f"unsupported detected media type {image_format!r} for {image_id}"
                raise ValueError(msg)
            image.verify()
        # Pillow requires ``verify`` immediately after open and invalidates the
        # verified instance. Reopen the bytes to read EXIF safely.
        with Image.open(BytesIO(data)) as image:
            capture = _merge_capture_metadata(image, declared)
    except (UnidentifiedImageError, OSError) as exc:
        msg = f"invalid image bytes for {image_id}"
        raise ValueError(msg) from exc
    return _FORMAT_TO_MEDIA[image_format], capture


def _merge_capture_metadata(
    image: Image.Image,
    declared: CaptureMetadataV1,
) -> CaptureMetadataV1:
    exif = image.getexif()
    orientation = exif.get(274)
    exif_orientation = orientation if isinstance(orientation, int) else None
    captured_at = declared.captured_at or _parse_exif_datetime(exif.get(36867))
    return CaptureMetadataV1(
        captured_at=captured_at,
        camera_make=declared.camera_make or _optional_text(exif.get(271)),
        camera_model=declared.camera_model or _optional_text(exif.get(272)),
        exif_orientation=declared.exif_orientation or exif_orientation,
    )


def _parse_exif_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

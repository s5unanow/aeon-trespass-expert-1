"""Image-set ingest preflight helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from pydantic import ValidationError

from atr_pipeline.utils.hashing import sha256_bytes, sha256_str
from atr_schemas.image_set_manifest_v1 import ImageSetImageV1, ImageSetManifestV1

_SUPPORTED_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class ImageSetIngestError(ValueError):
    """Raised when an image-set source fails preflight validation."""


@dataclass(frozen=True)
class PreparedImage:
    """A raw source image whose bytes and metadata passed preflight."""

    entry: ImageSetImageV1
    resolved_path: Path
    data: bytes


@dataclass(frozen=True)
class PreparedImageSet:
    """An image-set source ready for artifact registration."""

    manifest: ImageSetManifestV1
    manifest_path: Path
    manifest_sha256: str
    source_image_set_sha256: str
    images: tuple[PreparedImage, ...]


def prepare_image_set_source(*, manifest_path: Path, repo_root: Path) -> PreparedImageSet:
    """Validate an image-set manifest and read all image bytes before writes."""
    root = repo_root.resolve()
    manifest_real = _resolve_user_path(
        manifest_path,
        base_dir=root,
        repo_root=root,
        label="image_set_manifest",
    )
    manifest_bytes = _read_existing_file(manifest_real, label="image_set_manifest")
    try:
        manifest_data = json.loads(manifest_bytes.decode("utf-8"))
        manifest = ImageSetManifestV1.model_validate(manifest_data)
    except (UnicodeDecodeError, JSONDecodeError, ValidationError) as exc:
        msg = f"Malformed image-set manifest: {exc}"
        raise ImageSetIngestError(msg) from exc

    prepared: list[PreparedImage] = []
    seen_paths: set[Path] = set()
    for entry in manifest.images:
        image_path = _resolve_user_path(
            Path(entry.path),
            base_dir=manifest_real.parent,
            repo_root=root,
            label=f"image {entry.image_id}",
        )
        if image_path in seen_paths:
            msg = f"duplicate image path: {entry.path}"
            raise ImageSetIngestError(msg)
        seen_paths.add(image_path)

        _validate_media_type(entry, image_path)
        image_bytes = _read_existing_file(image_path, label=f"image {entry.image_id}")
        _validate_magic(entry, image_bytes)
        actual_sha = sha256_bytes(image_bytes)
        if actual_sha != entry.sha256:
            msg = (
                f"sha256 mismatch for {entry.image_id}: manifest={entry.sha256} actual={actual_sha}"
            )
            raise ImageSetIngestError(msg)
        expected_id = deterministic_image_id(entry.page_id, actual_sha)
        if entry.image_id != expected_id:
            msg = f"image_id for {entry.page_id} must be {expected_id}, got {entry.image_id}"
            raise ImageSetIngestError(msg)

        prepared.append(PreparedImage(entry=entry, resolved_path=image_path, data=image_bytes))

    return PreparedImageSet(
        manifest=manifest,
        manifest_path=manifest_real,
        manifest_sha256=sha256_bytes(manifest_bytes),
        source_image_set_sha256=_source_image_set_sha(prepared),
        images=tuple(prepared),
    )


def deterministic_image_id(page_id: str, sha256: str) -> str:
    """Return the deterministic raw-image id for a page/image hash pair."""
    return f"img.{page_id}.{sha256[:12]}"


def _source_image_set_sha(images: list[PreparedImage]) -> str:
    identity = [
        {
            "image_id": image.entry.image_id,
            "page_id": image.entry.page_id,
            "page_number": image.entry.page_number,
            "media_type": image.entry.media_type,
            "sha256": image.entry.sha256,
        }
        for image in images
    ]
    return sha256_str(json.dumps(identity, sort_keys=True, separators=(",", ":")))


def _resolve_user_path(path: Path, *, base_dir: Path, repo_root: Path, label: str) -> Path:
    text = str(path)
    if "\x00" in text:
        msg = f"{label} path contains a null byte"
        raise ImageSetIngestError(msg)
    if ".." in path.parts:
        msg = f"{label} path must not contain '..'"
        raise ImageSetIngestError(msg)

    candidate = path if path.is_absolute() else base_dir / path
    resolved = candidate.resolve(strict=False)
    allowed_roots = _allowed_roots(repo_root)
    if not any(_is_relative_to(resolved, allowed_root) for allowed_root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        msg = f"{label} path escapes allowed roots: {resolved} not under {roots}"
        raise ImageSetIngestError(msg)
    return resolved


def _allowed_roots(repo_root: Path) -> tuple[Path, ...]:
    materials_root = (repo_root / "materials").resolve(strict=False)
    if materials_root == repo_root:
        return (repo_root,)
    return (repo_root, materials_root)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_existing_file(path: Path, *, label: str) -> bytes:
    if not path.is_file():
        msg = f"{label} not found: {path}"
        raise ImageSetIngestError(msg)
    return path.read_bytes()


def _validate_media_type(entry: ImageSetImageV1, path: Path) -> None:
    expected_extension = _SUPPORTED_EXTENSIONS[entry.media_type]
    suffix = path.suffix.lower()
    if entry.media_type == "image/jpeg" and suffix == ".jpeg":
        return
    if suffix != expected_extension:
        msg = (
            f"unsupported media type or extension for {entry.image_id}: {entry.media_type} {suffix}"
        )
        raise ImageSetIngestError(msg)


def _validate_magic(entry: ImageSetImageV1, data: bytes) -> None:
    if entry.media_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    if entry.media_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff"):
        return
    msg = f"unsupported media bytes for {entry.image_id}: {entry.media_type}"
    raise ImageSetIngestError(msg)

"""Image-set ingest — validate, hash, and register photographed source images (S5U-780).

The entry point is :func:`ingest_image_set`, which:

1. **validates everything first** (path safety, media types, duplicates, missing
   files) via :func:`validate_image_set` — refusing before any artifact is
   written, so a rejected manifest leaves the store byte-for-byte untouched;
2. hashes each raw image's bytes and registers them as immutable ``source_image``
   artifacts through the existing store;
3. emits a :class:`~atr_schemas.source_manifest_v1.SourceManifestV1` whose
   per-image ``sha256`` fields and aggregate ``source_image_set_sha256`` are
   deterministic — producing byte-identical manifest JSON across runs on
   identical inputs.

Path safety (S5U-1536): manifest and image paths resolve via ``realpath`` (which
collapses ``..`` and follows symlinks) and must stay under the repository root.
Traversal, absolute escapes, symlink escapes, null bytes, unsupported media
types, duplicate image ids, and duplicate manifest entries are all refused.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import sha256_bytes, sha256_str
from atr_schemas.image_set_manifest_v1 import ImageSetImageEntry, ImageSetManifestV1
from atr_schemas.source_manifest_v1 import PageEntry, SourceImageRef, SourceManifestV1

# Decoded image format (Pillow ``Image.format``) → (media type, canonical extension).
# The media type is derived from the *content* Pillow decodes, never the on-disk
# filename extension, so a mislabelled file is caught rather than trusted.
_ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpeg"),
    "WEBP": ("image/webp", ".webp"),
    "TIFF": ("image/tiff", ".tiff"),
}


class ImageSetError(ValueError):
    """Raised when an image-set manifest or one of its images fails validation.

    Subclasses ``ValueError`` so the executor's generic failure path still
    records it while callers can catch it distinctly.
    """


@dataclass(frozen=True)
class ResolvedImage:
    """A manifest entry whose path and media type have passed validation."""

    entry: ImageSetImageEntry
    path: Path
    media_type: str
    extension: str
    width_px: int
    height_px: int


@dataclass(frozen=True)
class ValidatedImageSet:
    """A fully-validated image set, images ordered by ``(page_number, image_id)``."""

    manifest: ImageSetManifestV1
    images: list[ResolvedImage]


def _resolve_within_root(raw: str, *, base_dir: Path, repo_root: Path, label: str) -> Path:
    """Resolve ``raw`` and confirm it stays under ``repo_root``, or raise.

    ``realpath`` collapses ``..`` and follows symlinks, so the containment check
    below catches traversal, absolute escapes, and symlink escapes uniformly.
    """
    if "\x00" in raw:
        msg = f"{label} contains a null byte: {raw!r}"
        raise ImageSetError(msg)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    real = Path(os.path.realpath(candidate))
    root_real = Path(os.path.realpath(repo_root))
    if not real.is_relative_to(root_real):
        msg = f"{label} {raw!r} resolves to {real} which is outside the allowed root {root_real}"
        raise ImageSetError(msg)
    return real


def _probe_image(path: Path, image_id: str) -> tuple[str, str, int, int]:
    """Return ``(media_type, extension, width, height)`` or raise on unsupported input.

    Pillow reads the header only (no full decode). A file whose bytes are not a
    recognised image — including a text file wearing a ``.png`` name — raises
    ``UnidentifiedImageError``; a recognised-but-unsupported format (GIF/BMP/…)
    is rejected by the allow-list. Both are refusals, not silent passes.
    """
    try:
        with Image.open(path) as img:
            fmt = img.format
            width, height = img.size
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        # DecompressionBombError guards a maliciously huge decoded size; like the
        # other cases it becomes a clean refusal, never a partial write.
        msg = f"unsupported or unreadable image for {image_id!r}: {path} ({exc})"
        raise ImageSetError(msg) from exc
    if fmt not in _ALLOWED_FORMATS:
        msg = f"unsupported media type for {image_id!r}: decoded format {fmt!r} (path {path})"
        raise ImageSetError(msg)
    media_type, extension = _ALLOWED_FORMATS[fmt]
    return media_type, extension, int(width), int(height)


def _load_manifest(manifest_real: Path) -> ImageSetManifestV1:
    """Parse and schema-validate the manifest TOML, or raise ``ImageSetError``."""
    try:
        with open(manifest_real, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        msg = f"malformed image-set manifest {manifest_real}: {exc}"
        raise ImageSetError(msg) from exc
    try:
        return ImageSetManifestV1.model_validate(raw)
    except ValidationError as exc:
        msg = f"invalid image-set manifest {manifest_real}: {exc}"
        raise ImageSetError(msg) from exc


def validate_image_set(
    manifest_path: Path,
    *,
    repo_root: Path,
    document_id: str,
) -> ValidatedImageSet:
    """Validate an image-set manifest and every image it references — no writes.

    Every refusal case (traversal, absolute escape, null byte, unsupported media
    type, duplicate id, duplicate entry, malformed manifest, missing image)
    raises :class:`ImageSetError` before any artifact would be written.
    """
    manifest_real = _resolve_within_root(
        str(manifest_path), base_dir=repo_root, repo_root=repo_root, label="manifest path"
    )
    if not manifest_real.is_file():
        msg = f"image-set manifest not found: {manifest_real}"
        raise ImageSetError(msg)

    manifest = _load_manifest(manifest_real)
    if manifest.document_id != document_id:
        msg = (
            f"manifest document_id {manifest.document_id!r} does not match "
            f"config document {document_id!r}"
        )
        raise ImageSetError(msg)

    base_dir = manifest_real.parent
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    resolved: list[ResolvedImage] = []
    for entry in manifest.images:
        if entry.image_id in seen_ids:
            msg = f"duplicate image_id in manifest: {entry.image_id!r}"
            raise ImageSetError(msg)
        seen_ids.add(entry.image_id)

        img_real = _resolve_within_root(
            entry.path,
            base_dir=base_dir,
            repo_root=repo_root,
            label=f"image path for {entry.image_id!r}",
        )
        if img_real in seen_paths:
            msg = f"duplicate manifest entry: {img_real} referenced twice ({entry.image_id!r})"
            raise ImageSetError(msg)
        seen_paths.add(img_real)
        if not img_real.is_file():
            msg = f"image file not found for {entry.image_id!r}: {img_real}"
            raise ImageSetError(msg)

        media_type, extension, width, height = _probe_image(img_real, entry.image_id)
        resolved.append(
            ResolvedImage(
                entry=entry,
                path=img_real,
                media_type=media_type,
                extension=extension,
                width_px=width,
                height_px=height,
            )
        )

    resolved.sort(key=lambda r: (r.entry.page_number, r.entry.image_id))
    return ValidatedImageSet(manifest=manifest, images=resolved)


def _aggregate_sha256(per_image: list[tuple[str, str, int]]) -> str:
    """Deterministic aggregate fingerprint over ``(image_id, sha256, page_number)``.

    ``per_image`` is expected pre-sorted. Changing any single image's bytes
    changes its ``sha256`` and therefore this aggregate (cache invalidation);
    identical inputs reproduce it exactly (cache hit).
    """
    canonical = "\n".join(f"{iid}:{sha}:{pn}" for iid, sha, pn in per_image)
    return sha256_str(canonical)


def image_set_fingerprint(
    manifest_path: Path,
    *,
    repo_root: Path,
    document_id: str,
) -> str:
    """Compute the aggregate image-set fingerprint for the ingest cache key.

    Validates first (so a broken manifest is caught deterministically) then
    streams each image's bytes through ``sha256``. Used by
    ``IngestStage.extra_cache_inputs``; a failure there is surfaced by ``run``.
    """
    validated = validate_image_set(manifest_path, repo_root=repo_root, document_id=document_id)
    per_image = [
        (ri.entry.image_id, sha256_bytes(ri.path.read_bytes()), ri.entry.page_number)
        for ri in validated.images
    ]
    return _aggregate_sha256(per_image)


def ingest_image_set(
    *,
    store: ArtifactStore,
    document_id: str,
    manifest_path: Path,
    repo_root: Path,
    logger: logging.Logger,
) -> SourceManifestV1:
    """Validate, register raw images as immutable artifacts, and build the manifest."""
    validated = validate_image_set(manifest_path, repo_root=repo_root, document_id=document_id)
    logger.info("Ingesting image set for %s: %d image(s)", document_id, len(validated.images))

    image_refs: list[SourceImageRef] = []
    per_image: list[tuple[str, str, int]] = []
    for ri in validated.images:
        data = ri.path.read_bytes()
        sha = sha256_bytes(data)
        artifact_path = store.put_bytes(
            document_id=document_id,
            schema_family="source_image",
            scope="page",
            entity_id=ri.entry.image_id,
            data=data,
            extension=ri.extension,
        )
        artifact_ref = str(artifact_path.relative_to(store.root))
        logger.info(
            "Registered source image %s (%s, %dx%d) -> %s",
            ri.entry.image_id,
            ri.media_type,
            ri.width_px,
            ri.height_px,
            artifact_ref,
        )
        image_refs.append(
            SourceImageRef(
                image_id=ri.entry.image_id,
                sha256=sha,
                page_number=ri.entry.page_number,
                media_type=ri.media_type,
                extension=ri.extension,
                width_px=ri.width_px,
                height_px=ri.height_px,
                artifact_ref=artifact_ref,
            )
        )
        per_image.append((ri.entry.image_id, sha, ri.entry.page_number))

    page_numbers = sorted({ri.entry.page_number for ri in validated.images})
    pages = [PageEntry(page_id=f"p{n:04d}", page_number=n) for n in page_numbers]
    return SourceManifestV1(
        document_id=document_id,
        source_kind="image_set",
        source_image_set_sha256=_aggregate_sha256(per_image),
        page_count=len(pages),
        pages=pages,
        images=image_refs,
    )

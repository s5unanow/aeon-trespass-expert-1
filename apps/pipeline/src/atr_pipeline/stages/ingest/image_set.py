"""Image-set ingest logic (S5U-1535).

Handles path-safe loading of an ImageSetManifestV1, validation of all
referenced images, registration of raw image bytes + metadata as immutable
artifacts, computation of deterministic IDs and source fingerprint, and
emission of SourceManifestV1.

All safety checks (traversal, roots, null bytes, media types, duplicates)
happen **before** any write to the artifact store.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import sha256_bytes
from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1
from atr_schemas.source_ref_v1 import ImageEntryV1, ImageSetManifestV1

# Allowed media type extensions for raw page images (case-insensitive).
_ALLOWED_IMAGE_EXTS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# Roots under which image paths (after realpath resolution) must reside.
# repo_root is always allowed; "materials" is conventional for large assets.
_ALLOWED_ROOT_NAMES = ("materials",)


def _is_safe_under_roots(resolved: Path, allowed_roots: Iterable[Path]) -> bool:
    """Return True iff resolved path is inside at least one allowed root."""
    try:
        for root in allowed_roots:
            root_r = root.resolve()
            # relative_to raises if not under
            resolved.relative_to(root_r)
            return True
    except Exception:
        pass
    return False


def resolve_safe_path(
    *,
    candidate: str,
    repo_root: Path,
    allowed_extra_roots: Iterable[Path] | None = None,
) -> Path:
    """Resolve candidate to a real path and enforce safety constraints.

    Rules (fail fast, no partial state):
    - Reject null bytes anywhere in candidate.
    - Reject paths containing literal ".." segments (defense in depth).
    - Resolve via Path.resolve() (follows symlinks, normalizes).
    - Final resolved path must be under repo_root or one of the allowed
      extra roots (e.g. materials/).
    - Absolute paths that escape the allowed set are rejected.

    Returns the resolved Path on success. Raises ValueError with a clear
    message on any violation.
    """
    if "\x00" in candidate:
        msg = "Path contains null byte"
        raise ValueError(msg)

    # Quick traversal marker rejection before filesystem work.
    # We still do full realpath + under-root check below.
    if ".." in Path(candidate).parts:
        msg = f"Path escapes allowed roots (contains ..): {candidate}"
        raise ValueError(msg)

    p = Path(candidate)
    resolved = p.resolve() if p.is_absolute() else (repo_root / p).resolve()

    allowed = [repo_root, *(allowed_extra_roots or [])]
    # Also allow conventional materials/ sibling or child of repo_root
    for name in _ALLOWED_ROOT_NAMES:
        cand = repo_root / name
        if cand.exists() or True:  # existence not required to allow the subtree
            allowed.append(cand)

    if not _is_safe_under_roots(resolved, allowed):
        msg = f"Resolved path {resolved} is outside allowed roots (repo_root={repo_root})"
        raise ValueError(msg)

    return resolved


def _load_image_set_manifest(manifest_path: Path) -> ImageSetManifestV1:
    """Load and basic-validate the image set manifest JSON."""
    if not manifest_path.exists():
        msg = f"Image-set manifest not found: {manifest_path}"
        raise FileNotFoundError(msg)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Malformed image-set manifest JSON: {exc}"
        raise ValueError(msg) from exc

    return ImageSetManifestV1.model_validate(raw)


def _media_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".png"}:
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".webp"}:
        return "image/webp"
    return "application/octet-stream"


def _validate_image_file(path: Path) -> None:
    """Check extension whitelist and that file is a regular readable file."""
    if not path.is_file():
        msg = f"Image path does not exist or is not a file: {path}"
        raise FileNotFoundError(msg)
    ext = path.suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        msg = f"Unsupported media type for image-set page: {ext} ({path.name})"
        raise ValueError(msg)


def register_image_set(
    *,
    document_id: str,
    manifest_path: Path,
    repo_root: Path,
    store: ArtifactStore,
) -> tuple[SourceManifestV1, str]:
    """Validate, register raw images, and return a SourceManifestV1 + set fingerprint.

    All refusal conditions are checked and raised before any artifact is written.

    Determinism: page order from the manifest is preserved. page_id values
    (pNNNN) are taken from the manifest (they are the source of truth for
    deterministic identity). The returned SourceManifestV1 has stable JSON
    for identical inputs.
    """
    # 1. Resolve manifest safely
    resolved_manifest = resolve_safe_path(
        candidate=str(manifest_path),
        repo_root=repo_root,
    )

    # 2. Load manifest (structured validation)
    manifest = _load_image_set_manifest(resolved_manifest)
    if not manifest.images:
        msg = "Image-set manifest contains no images"
        raise ValueError(msg)

    # 3. Collect and validate every referenced image (no writes yet)
    seen_ids: set[str] = set()
    entries: list[ImageEntryV1] = []
    raw_pages: list[tuple[str, bytes, Path]] = []  # (page_id, data, resolved_path)

    manifest_dir = resolved_manifest.parent

    for img in manifest.images:
        page_id = img.page_id
        if page_id in seen_ids:
            msg = f"Duplicate image ID in manifest: {page_id}"
            raise ValueError(msg)
        seen_ids.add(page_id)

        # Resolve image path relative to manifest location (or repo if absolute)
        cand = img.path
        if "\x00" in cand:
            msg = f"Image path contains null byte: {page_id}"
            raise ValueError(msg)
        if ".." in Path(cand).parts:
            msg = f"Image path escapes (contains ..): {page_id} {cand}"
            raise ValueError(msg)

        ip = Path(cand)
        resolved_img = (manifest_dir / ip).resolve() if not ip.is_absolute() else ip.resolve()

        # Enforce under-root for the image itself
        allowed_roots = [repo_root, manifest_dir, repo_root / "materials"]
        if not _is_safe_under_roots(resolved_img, allowed_roots):
            msg = f"Image path resolves outside allowed roots: {page_id} -> {resolved_img}"
            raise ValueError(msg)

        _validate_image_file(resolved_img)

        data = resolved_img.read_bytes()
        sha = sha256_bytes(data)
        media = _media_type_for(resolved_img)

        # Fill sha into a copy of the entry for the manifest echo
        filled = img.model_copy(update={"sha256": sha, "media_type": media})
        entries.append(filled)
        raw_pages.append((page_id, data, resolved_img))

    # 4. Compute a stable source fingerprint for the whole set.
    # Use a canonical string of "page_id:sha256" lines sorted by page_id.
    fingerprint_src = "\n".join(sorted(f"{e.page_id}:{e.sha256}" for e in entries))
    source_set_sha = sha256_bytes(fingerprint_src.encode("utf-8"))

    # 5. NOW safe to write artifacts (all checks passed).
    page_entries: list[PageEntry] = []
    image_entries_for_manifest: list[ImageEntryV1] = []

    for idx, (page_id, data, resolved_img) in enumerate(raw_pages, start=1):
        page_number = idx
        # Register the pristine source bytes (content-addressed; idempotent).
        # Use schema_family "source_image" to distinguish from derived rasters.
        store.put_bytes(
            document_id=document_id,
            schema_family="source_image",
            scope="page",
            entity_id=page_id,
            data=data,
            extension=resolved_img.suffix.lower() or ".bin",
        )

        page_entries.append(PageEntry(page_id=page_id, page_number=page_number, raster_ref=None))
        # Find the filled entry
        filled = next(e for e in entries if e.page_id == page_id)
        image_entries_for_manifest.append(filled)

    # Build the emitted source manifest (page list + fingerprints).
    # page_count derived from provided images.
    manifest_out = SourceManifestV1(
        document_id=document_id,
        source_pdf_sha256="",
        source_image_set_sha256=source_set_sha,
        page_count=len(page_entries),
        pages=page_entries,
        image_entries=image_entries_for_manifest,
    )

    return manifest_out, source_set_sha

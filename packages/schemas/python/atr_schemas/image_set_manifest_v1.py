"""ImageSetManifestV1 — authoring manifest for a photographed image-set source.

This is the human-authored (or tool-generated) manifest that an ``image_set``
document config points at. It lists the ordered source images that make up a
document — e.g. photographed pages of a physical book — together with per-image
capture/EXIF metadata and the page each image belongs to.

It is the *input* to the ingest stage (S5U-780). Ingest resolves each ``path``
against the manifest's directory, hashes the raw bytes, registers them as
immutable artifacts, and emits a :class:`~atr_schemas.source_manifest_v1.SourceManifestV1`
whose per-image ``sha256`` fields are the *output* fingerprints. Nothing here
carries a content hash — the manifest describes *which* files to ingest, not
their bytes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CaptureMetadata(BaseModel):
    """Optional EXIF/capture metadata for a single photographed image.

    Every field is optional — a synthetic or metadata-stripped image simply
    omits them. ``exif`` is a free-form bag for tags not modelled explicitly so
    a capture pipeline can preserve provenance without a schema change.
    """

    camera_make: str = ""
    camera_model: str = ""
    captured_at: str = ""
    """ISO-8601 capture timestamp, if known."""
    orientation: int | None = Field(default=None, ge=1, le=8)
    """EXIF orientation tag (1-8), if known."""
    exif: dict[str, str] = Field(default_factory=dict)
    """Additional EXIF tags as string key/value pairs."""


class ImageSetImageEntry(BaseModel):
    """One source image in the ordered image set."""

    image_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
        description=(
            "Stable, author-supplied identifier for this image. Must be unique "
            "within the manifest; ingest refuses duplicates. Used verbatim as "
            "the artifact entity id, so it is restricted to a filesystem-safe "
            "charset."
        ),
    )
    path: str = Field(
        description=(
            "Relative path to the image file, resolved against the manifest's "
            "own directory. Must stay under the repository root after realpath "
            "resolution — ingest refuses traversal, absolute escapes, and "
            "symlink escapes."
        ),
    )
    page_number: int = Field(ge=1, description="1-based page this image belongs to.")
    media_type: str = Field(
        default="",
        description=(
            "Optional IANA media type hint (e.g. ``image/png``). When empty, "
            "ingest derives it from the decoded image format."
        ),
    )
    capture: CaptureMetadata | None = None


class ImageSetManifestV1(BaseModel):
    """Ordered manifest of source images for an ``image_set`` document."""

    schema_version: str = Field(
        default="image_set_manifest.v1",
        pattern=r"^image_set_manifest\.v\d+$",
    )
    document_id: str
    images: list[ImageSetImageEntry] = Field(min_length=1)

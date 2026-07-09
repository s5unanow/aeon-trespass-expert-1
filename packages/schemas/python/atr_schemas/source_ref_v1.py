"""Source reference abstraction (discriminated union) and image-set manifest (S5U-1535).

This module defines the Pydantic source abstraction used by DocumentConfig
and the ingest stage. A SourceRefV1 is either a PDF source or an image-set
source. Image-set sources are described by an on-disk ImageSetManifestV1
that lists ordered page images with deterministic IDs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class PdfSourceV1(BaseModel):
    """PDF document source (normalizes from legacy document.source_pdf)."""

    source_kind: Literal["pdf"] = "pdf"
    path: str


class ImageEntryV1(BaseModel):
    """Descriptor for one page image within an image-set source.

    - page_id uses the canonical pNNNN form for stable page identity.
    - sha256 is the hex digest of the raw image file bytes (filled by ingest).
    - path is relative to the manifest or repo root (resolved safely at ingest).
    """

    page_id: str = Field(pattern=r"^p\d{4}$")
    path: str
    sha256: str | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    media_type: str | None = None


class ImageSetManifestV1(BaseModel):
    """On-disk manifest describing the ordered images for an image-set source.

    This is the input artifact referenced by an ImageSetSourceV1.
    It is validated for duplicates, path safety (by ingest), and media types
    before any raw image bytes are registered as artifacts.
    """

    schema_version: str = Field(
        default="image_set_manifest.v1", pattern=r"^image_set_manifest\.v\d+$"
    )
    images: list[ImageEntryV1]


class ImageSetSourceV1(BaseModel):
    """Image-set (e.g. photographed physical pages) document source."""

    source_kind: Literal["image_set"] = "image_set"
    manifest_path: str


SourceRefV1 = Annotated[
    PdfSourceV1 | ImageSetSourceV1,
    Field(discriminator="source_kind"),
]

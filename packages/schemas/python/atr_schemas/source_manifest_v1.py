"""SourceManifestV1 — registered source document and pages."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Import here to avoid circulars at module load while sharing the entry type.
from atr_schemas.source_ref_v1 import ImageEntryV1


class PageEntry(BaseModel):
    """Metadata for a single source page."""

    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    raster_ref: str | None = None


class SourceManifestV1(BaseModel):
    """Registered source document and its pages.

    PDF sources populate source_pdf_sha256 (historical field).
    Image-set sources populate the complement source_image_set_sha256 and
    may list per-image details in image_entries. The two fingerprint fields
    coexist; neither overloads the other.
    """

    schema_version: str = Field(default="source_manifest.v1", pattern=r"^source_manifest\.v\d+$")
    document_id: str
    source_pdf_sha256: str = ""
    page_count: int = Field(ge=1)
    pages: list[PageEntry]
    config_hash: str = ""
    extractor_version: str = ""

    # Image-set complement (S5U-1535). Empty for PDF sources.
    source_image_set_sha256: str = ""
    image_entries: list[ImageEntryV1] = Field(default_factory=list)

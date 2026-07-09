"""SourceManifestV1 — registered source document and pages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from atr_schemas.image_set_manifest_v1 import ImageSetManifestV1


class PageEntry(BaseModel):
    """Metadata for a single source page."""

    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    raster_ref: str | None = None
    source_image_id: str | None = None
    raw_image_ref: str | None = None


class SourceManifestV1(BaseModel):
    """Registered source document and its pages."""

    schema_version: str = Field(default="source_manifest.v1", pattern=r"^source_manifest\.v\d+$")
    document_id: str
    source_kind: Literal["pdf", "image_set"] = "pdf"
    source_pdf_sha256: str = ""
    source_image_set_sha256: str = ""
    source_image_set_manifest_sha256: str = ""
    page_count: int = Field(ge=1)
    pages: list[PageEntry]
    image_set: ImageSetManifestV1 | None = None
    config_hash: str = ""
    extractor_version: str = ""

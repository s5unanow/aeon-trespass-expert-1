"""SourceManifestV1 — registered source document and pages."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageEntry(BaseModel):
    """Metadata for a single source page."""

    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    raster_ref: str | None = None


class SourceManifestV1(BaseModel):
    """Registered source document and its pages."""

    schema_version: str = Field(default="source_manifest.v1", pattern=r"^source_manifest\.v\d+$")
    document_id: str
    source_pdf_sha256: str
    page_count: int = Field(ge=1)
    pages: list[PageEntry]
    config_hash: str = ""
    extractor_version: str = ""

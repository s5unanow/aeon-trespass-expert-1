"""RasterMetaV1 — provenance metadata for rendered page rasters."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RasterLevel(BaseModel):
    """Metadata for a single raster resolution level."""

    dpi: int = Field(ge=72)
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    content_hash: str
    relative_path: str = Field(description="Path relative to artifact root")


class RasterMetaV1(BaseModel):
    """Provenance metadata for all rendered raster levels of a page."""

    schema_version: str = Field(
        default="raster_meta.v1",
        pattern=r"^raster_meta\.v\d+$",
    )
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    source_pdf_sha256: str
    render_engine: str = "pymupdf"
    render_engine_version: str = ""
    levels: list[RasterLevel] = Field(default_factory=list)

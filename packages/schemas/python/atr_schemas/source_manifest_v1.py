"""SourceManifestV1 — registered source document and pages.

A single manifest schema covers both source kinds (S5U-780). PDF sources set
``source_pdf_sha256`` (unchanged); image-set sources set ``source_kind =
"image_set"``, ``source_image_set_sha256`` (an aggregate fingerprint that
*complements* — never overloads — ``source_pdf_sha256``), and one
:class:`SourceImageRef` per registered raw image. Every image-set field is
defaulted so a PDF manifest serialises exactly as before.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PageEntry(BaseModel):
    """Metadata for a single source page."""

    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    raster_ref: str | None = None


class SourceImageRef(BaseModel):
    """A raw source image registered by image-set ingest.

    ``sha256`` is the hex digest of the raw file bytes as stored (the artifact
    is content-addressed by the same digest). ``artifact_ref`` is the relative
    path within the artifact store.
    """

    image_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    media_type: str
    extension: str = Field(description="File extension including the leading dot.")
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    artifact_ref: str = ""


class SourceManifestV1(BaseModel):
    """Registered source document and its pages."""

    schema_version: str = Field(default="source_manifest.v1", pattern=r"^source_manifest\.v\d+$")
    document_id: str
    source_kind: Literal["pdf", "image_set"] = "pdf"
    source_pdf_sha256: str = ""
    source_image_set_sha256: str = ""
    page_count: int = Field(ge=1)
    pages: list[PageEntry]
    images: list[SourceImageRef] = Field(default_factory=list)
    config_hash: str = ""
    extractor_version: str = ""

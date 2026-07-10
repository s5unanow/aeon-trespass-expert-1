"""SourceManifestV1 — registered source document and pages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from atr_schemas.image_set_manifest_v1 import CaptureMetadataV1, ImageMediaType


class PageEntry(BaseModel):
    """Metadata for a single source page."""

    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    raster_ref: str | None = None


class SourceImageEntryV1(BaseModel):
    """Registered immutable raw image and its source-page mapping."""

    image_id: str = Field(pattern=r"^img\.[a-z0-9][a-z0-9._-]*$")
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    media_type: ImageMediaType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_artifact_ref: str = Field(min_length=1)
    capture: CaptureMetadataV1 = Field(default_factory=CaptureMetadataV1)


class SourceManifestV1(BaseModel):
    """Registered source document and its pages."""

    schema_version: str = Field(default="source_manifest.v1", pattern=r"^source_manifest\.v\d+$")
    document_id: str
    source_kind: Literal["pdf", "image_set"] = "pdf"
    source_pdf_sha256: str
    source_manifest_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    source_image_set_sha256: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    page_count: int = Field(ge=1)
    pages: list[PageEntry]
    source_images: list[SourceImageEntryV1] = Field(default_factory=list)
    config_hash: str = ""
    extractor_version: str = ""

    @model_validator(mode="after")
    def _validate_source_identity(self) -> SourceManifestV1:
        if self.source_kind == "pdf":
            if self.source_manifest_sha256 or self.source_image_set_sha256 or self.source_images:
                msg = "PDF source image-set fields must be empty"
                raise ValueError(msg)
            return self

        if self.source_pdf_sha256:
            msg = "source_pdf_sha256 must be empty for image_set source"
            raise ValueError(msg)
        if not self.source_manifest_sha256 or not self.source_image_set_sha256:
            msg = "image_set source requires manifest and image-set fingerprints"
            raise ValueError(msg)
        if len(self.source_images) != self.page_count:
            msg = "image_set source_images must contain one entry per page"
            raise ValueError(msg)
        page_mapping = [(page.page_id, page.page_number) for page in self.pages]
        image_mapping = [(image.page_id, image.page_number) for image in self.source_images]
        if image_mapping != page_mapping:
            msg = "image_set source image page mapping must match pages"
            raise ValueError(msg)
        return self

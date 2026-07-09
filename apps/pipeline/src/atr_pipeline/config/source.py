"""Document source configuration models."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class PdfSourceConfig(BaseModel):
    """PDF source configuration."""

    source_kind: Literal["pdf"] = "pdf"
    source_pdf: str = ""


class ImageSetSourceConfig(BaseModel):
    """Image-set source configuration."""

    source_kind: Literal["image_set"] = "image_set"
    manifest_path: str


SourceConfig = Annotated[PdfSourceConfig | ImageSetSourceConfig, Field(discriminator="source_kind")]


class DocumentConfig(BaseModel):
    """Document-specific configuration."""

    id: str
    source_pdf: str = ""
    source: SourceConfig = Field(default_factory=PdfSourceConfig)
    source_lang: str = "en"
    target_langs: list[str] = Field(default_factory=lambda: ["ru"])
    structure_builder: Literal["real", "simple"] = "real"

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_source(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "source" in normalized:
            return normalized

        source_kind = normalized.get("source_kind")
        if source_kind is None:
            normalized["source"] = {
                "source_kind": "pdf",
                "source_pdf": str(normalized.get("source_pdf", "")),
            }
            return normalized
        if source_kind == "pdf":
            normalized["source"] = {
                "source_kind": "pdf",
                "source_pdf": str(normalized.get("source_pdf", "")),
            }
            return normalized
        if source_kind == "image_set":
            normalized["source"] = {
                "source_kind": "image_set",
                "manifest_path": str(normalized.get("image_set_manifest", "")),
            }
            return normalized

        normalized["source"] = {"source_kind": source_kind}
        return normalized

    @model_validator(mode="after")
    def _sync_legacy_fields(self) -> DocumentConfig:
        if isinstance(self.source, PdfSourceConfig):
            object.__setattr__(self, "source_pdf", self.source.source_pdf)
        else:
            object.__setattr__(self, "source_pdf", "")
        return self

    @property
    def source_kind(self) -> Literal["pdf", "image_set"]:
        """Normalized source kind."""
        return self.source.source_kind

    @property
    def image_set_manifest(self) -> str:
        """Image-set manifest path for image-set sources, else empty."""
        if isinstance(self.source, ImageSetSourceConfig):
            return self.source.manifest_path
        return ""

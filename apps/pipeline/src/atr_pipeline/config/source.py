"""Document source variants and legacy configuration normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field, model_validator


class PdfSourceConfig(BaseModel):
    """A born-digital PDF source."""

    source_kind: Literal["pdf"] = "pdf"
    path: str


class ImageSetSourceConfig(BaseModel):
    """An ordered set of photographed source pages."""

    source_kind: Literal["image_set"] = "image_set"
    manifest_path: str


DocumentSourceConfig = Annotated[
    PdfSourceConfig | ImageSetSourceConfig,
    Field(discriminator="source_kind"),
]


class DocumentConfig(BaseModel):
    """Document-specific configuration with a normalized source variant."""

    id: str
    source: DocumentSourceConfig
    source_pdf: str | None = Field(default=None, exclude=True)
    source_manifest: str | None = Field(default=None, exclude=True)
    source_lang: str = "en"
    target_langs: list[str] = Field(default_factory=lambda: ["ru"])
    structure_builder: Literal["real", "simple"] = "real"

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_source(cls, data: object) -> object:
        """Convert legacy and flat TOML keys into the tagged source union."""
        if not isinstance(data, Mapping):
            return data
        values = dict(cast(Mapping[str, object], data))
        if "source" in values:
            return values

        source_kind = values.get("source_kind")
        if source_kind is None and "source_pdf" in values:
            source_kind = "pdf"

        if source_kind == "pdf":
            values["source"] = {
                "source_kind": "pdf",
                "path": values.get("source_pdf"),
            }
        elif source_kind == "image_set":
            values["source"] = {
                "source_kind": "image_set",
                "manifest_path": values.get("source_manifest"),
            }
        elif source_kind is not None:
            # Preserve the unknown tag so Pydantic's discriminator emits a
            # clear, fail-closed validation error naming ``source_kind``.
            values["source"] = {"source_kind": source_kind}
        return values

    @model_validator(mode="after")
    def _sync_compatibility_paths(self) -> DocumentConfig:
        """Expose normalized paths through the legacy compatibility fields."""
        if isinstance(self.source, PdfSourceConfig):
            if self.source_pdf is not None and self.source_pdf != self.source.path:
                msg = "source_pdf conflicts with source.path"
                raise ValueError(msg)
            object.__setattr__(self, "source_pdf", self.source.path)
            object.__setattr__(self, "source_manifest", None)
        else:
            if self.source_pdf is not None:
                msg = "image_set source cannot define source_pdf"
                raise ValueError(msg)
            if (
                self.source_manifest is not None
                and self.source_manifest != self.source.manifest_path
            ):
                msg = "source_manifest conflicts with source.manifest_path"
                raise ValueError(msg)
            object.__setattr__(self, "source_manifest", self.source.manifest_path)
        return self

"""SymbolCatalogV1 — known icon definitions and matching configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolEntry(BaseModel):
    """A single symbol definition in the catalog."""

    symbol_id: str
    label: str
    alt_label_ru: str = ""
    template_asset: str = ""
    match_threshold: float = Field(default=0.93, ge=0.0, le=1.0)
    inline: bool = True


class SymbolCatalogV1(BaseModel):
    """Catalog of known symbols for matching."""

    schema_version: str = Field(
        default="symbol_catalog.v1", pattern=r"^symbol_catalog\.v\d+$"
    )
    catalog_id: str = ""
    version: str = ""
    symbols: list[SymbolEntry] = Field(default_factory=list)

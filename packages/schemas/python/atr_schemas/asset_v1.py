"""AssetV1 — extracted assets and crops."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import Rect
from atr_schemas.enums import AssetKind


class AssetVariant(BaseModel):
    """A size/format variant of an asset."""

    variant: str  # original, web, thumb, sprite
    path: str = ""
    mime_type: str = ""
    width_px: int = 0
    height_px: int = 0


class AssetV1(BaseModel):
    """An extracted or catalogued asset (figure, inline symbol, etc.)."""

    schema_version: str = Field(default="asset.v1", pattern=r"^asset\.v\d+$")
    asset_id: str
    kind: AssetKind
    mime_type: str = "image/png"
    source_page_id: str = ""
    bbox: Rect | None = None
    sha256: str = ""
    phash: str = ""
    pixel_size: dict[str, int] = Field(default_factory=dict)
    catalog_binding: str | None = None
    variants: list[AssetVariant] = Field(default_factory=list)
    placement_hint: dict[str, object] = Field(default_factory=dict)
    caption_block_id: str | None = None

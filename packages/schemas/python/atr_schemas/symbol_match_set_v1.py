"""SymbolMatchSetV1 — page-level symbol detection results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import Rect


class SymbolMatch(BaseModel):
    """A single detected symbol match on a page."""

    symbol_id: str
    instance_id: str = ""
    bbox: Rect
    score: float = Field(ge=0.0, le=1.0)
    source_asset_id: str = ""
    inline: bool = True


class SymbolMatchSetV1(BaseModel):
    """All symbol detections for a single page."""

    schema_version: str = Field(default="symbol_match_set.v1", pattern=r"^symbol_match_set\.v\d+$")
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    matches: list[SymbolMatch] = Field(default_factory=list)
    unmatched_candidates: int = 0

"""LayoutPageV1 — secondary layout evidence per page."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import Rect


class LayoutZone(BaseModel):
    """A detected layout zone on a page."""

    zone_id: str
    kind: str = ""  # body, sidebar, footer, figure, header, etc.
    bbox: Rect
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DifficultyScoreV1(BaseModel):
    """Per-page difficulty classification."""

    page_id: str
    column_count: int = 1
    zone_overlap_ratio: float = 0.0
    native_text_coverage: float = 1.0
    extractor_agreement: float = 1.0
    hard_page: bool = False
    recommended_route: str = "R1"


class LayoutPageV1(BaseModel):
    """Secondary layout evidence for a single page."""

    schema_version: str = Field(default="layout_page.v1", pattern=r"^layout_page\.v\d+$")
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    zones: list[LayoutZone] = Field(default_factory=list)
    reading_order_candidates: list[list[str]] = Field(default_factory=list)
    difficulty: DifficultyScoreV1 | None = None

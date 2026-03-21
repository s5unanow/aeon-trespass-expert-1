"""AssetOccurrenceV1 — one placement of an asset class on a specific page."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import OccurrenceContext


class AssetOccurrenceV1(BaseModel):
    """A single placement of an asset on a page.

    Each occurrence references its parent :class:`AssetClassV1` via
    ``class_id`` and the underlying evidence entities via ``evidence_ids``.
    """

    occurrence_id: str = Field(
        description="Unique per occurrence, e.g. ao.p0042.001",
    )
    class_id: str = Field(
        description="References the parent AssetClassV1.class_id.",
    )
    page_id: str = Field(pattern=r"^p\d{4}$")
    bbox: Rect
    norm_bbox: NormRect
    context: OccurrenceContext = OccurrenceContext.INLINE
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

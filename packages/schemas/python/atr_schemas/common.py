"""Shared primitive types used across all ATR schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class Rect(BaseModel):
    """Bounding box in PDF points: [x0, y0, x1, y1]."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class PageDimensions(BaseModel):
    """Source page dimensions in PDF points."""

    width: float
    height: float


class ProvenanceRef(BaseModel):
    """Reference to upstream evidence or extraction source."""

    extractor: str
    version: str
    evidence_ids: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    """Pointer to an immutable artifact in the store."""

    schema_family: str
    scope: str
    entity_id: str
    content_hash: str
    path: str


class ConfidenceMetrics(BaseModel):
    """Per-page confidence scores."""

    native_text_coverage: float = Field(ge=0.0, le=1.0)
    reading_order_score: float = Field(ge=0.0, le=1.0, default=1.0)
    symbol_score: float = Field(ge=0.0, le=1.0, default=1.0)
    page_confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class QAState(BaseModel):
    """Page-level QA status summary."""

    blocking: bool = False
    errors: int = 0
    warnings: int = 0


class NormRect(BaseModel):
    """Bounding box in normalized [0,1] page coordinate space."""

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)


# Commonly used annotated types
PageId = Annotated[str, Field(pattern=r"^p\d{4}$", description="Page id like p0001")]
BlockId = Annotated[str, Field(pattern=r"^p\d{4}\.b\d{3}$", description="Block id like p0001.b001")]
DocumentId = Annotated[str, Field(min_length=1, description="Stable document edition id")]
Timestamp = Annotated[datetime, Field(description="ISO 8601 timestamp")]
EvidenceId = Annotated[
    str, Field(pattern=r"^e\.\w+\.\d{3,}$", description="Evidence id like e.char.001")
]
RegionId = Annotated[str, Field(pattern=r"^r\d{3}$", description="Region id like r001")]

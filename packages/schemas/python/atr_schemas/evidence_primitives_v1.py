"""Evidence primitive entity models for the extraction evidence layer.

Each entity represents a raw observation on a page — no semantic
interpretation.  Every entity carries a stable ``evidence_id`` and
bounding boxes in both PDF-point and normalised [0,1] coordinate spaces.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import RegionKind

# --- Individual evidence entity models ---


class EvidenceChar(BaseModel):
    """A single character glyph extracted from the PDF."""

    kind: Literal["char"] = "char"
    evidence_id: str
    text: str
    bbox: Rect
    norm_bbox: NormRect
    font_name: str = ""
    font_size: float = 0.0
    flags: int = 0
    color: int = 0


class EvidenceLine(BaseModel):
    """A line of text (sequence of characters)."""

    kind: Literal["line"] = "line"
    evidence_id: str
    text: str
    bbox: Rect
    norm_bbox: NormRect
    char_ids: list[str] = Field(default_factory=list)
    writing_direction: str = "ltr"


class EvidenceTextSpan(BaseModel):
    """A formatting-consistent text span."""

    kind: Literal["text_span"] = "text_span"
    evidence_id: str
    text: str
    bbox: Rect
    norm_bbox: NormRect
    font_name: str = ""
    font_size: float = 0.0
    flags: int = 0
    color: int = 0
    char_ids: list[str] = Field(default_factory=list)


class EvidenceImageOccurrence(BaseModel):
    """An image placed on the page."""

    kind: Literal["image_occurrence"] = "image_occurrence"
    evidence_id: str
    bbox: Rect
    norm_bbox: NormRect
    width_px: int = 0
    height_px: int = 0
    colorspace: str = ""
    xref: int = 0
    image_hash: str = ""


class EvidenceVectorPath(BaseModel):
    """A single vector drawing path."""

    kind: Literal["vector_path"] = "vector_path"
    evidence_id: str
    bbox: Rect
    norm_bbox: NormRect
    path_ops: list[str] = Field(default_factory=list)
    stroke_color: int | None = None
    fill_color: int | None = None
    line_width: float = 0.0


class EvidenceVectorCluster(BaseModel):
    """A cluster of related vector paths."""

    kind: Literal["vector_cluster"] = "vector_cluster"
    evidence_id: str
    bbox: Rect
    norm_bbox: NormRect
    path_ids: list[str] = Field(default_factory=list)
    cluster_hash: str = ""


class EvidenceTableCandidate(BaseModel):
    """A detected table-like structure."""

    kind: Literal["table_candidate"] = "table_candidate"
    evidence_id: str
    bbox: Rect
    norm_bbox: NormRect
    row_count: int = 0
    col_count: int = 0
    cell_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class EvidenceRegionCandidate(BaseModel):
    """A spatial region detected from layout analysis."""

    kind: Literal["region_candidate"] = "region_candidate"
    evidence_id: str
    bbox: Rect
    norm_bbox: NormRect
    region_kind: RegionKind = RegionKind.UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source_zone_id: str = ""


# --- Discriminated union ---


def _get_evidence_discriminator(v: dict[str, object] | BaseModel) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", ""))
    return str(getattr(v, "kind", ""))


EvidenceEntity = Annotated[
    Annotated[EvidenceChar, Tag("char")]
    | Annotated[EvidenceLine, Tag("line")]
    | Annotated[EvidenceTextSpan, Tag("text_span")]
    | Annotated[EvidenceImageOccurrence, Tag("image_occurrence")]
    | Annotated[EvidenceVectorPath, Tag("vector_path")]
    | Annotated[EvidenceVectorCluster, Tag("vector_cluster")]
    | Annotated[EvidenceTableCandidate, Tag("table_candidate")]
    | Annotated[EvidenceRegionCandidate, Tag("region_candidate")],
    Discriminator(_get_evidence_discriminator),
]

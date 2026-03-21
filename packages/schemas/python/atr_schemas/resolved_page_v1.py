"""ResolvedPageV1 — semantic resolution graph referencing evidence entities."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import NormRect, ProvenanceRef, Rect, RegionId
from atr_schemas.enums import AnchorEdgeKind, BlockType, RegionKind, SymbolAnchorKind


class ResolvedRegion(BaseModel):
    """A semantic region/zone on the resolved page."""

    region_id: RegionId
    kind: RegionKind
    bbox: Rect
    norm_bbox: NormRect
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class AnchorEdge(BaseModel):
    """Directed relationship between two resolved entities."""

    edge_kind: AnchorEdgeKind
    source_id: str
    target_id: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ResolvedSymbolRef(BaseModel):
    """A symbol occurrence resolved from evidence."""

    symbol_id: str
    instance_id: str = ""
    anchor_kind: SymbolAnchorKind
    evidence_ids: list[str] = Field(default_factory=list)
    bbox: Rect | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class SemanticConfidence(BaseModel):
    """Per-aspect confidence scores for the resolution process."""

    overall: float = Field(ge=0.0, le=1.0, default=1.0)
    region_segmentation: float = Field(ge=0.0, le=1.0, default=1.0)
    reading_order: float = Field(ge=0.0, le=1.0, default=1.0)
    block_classification: float = Field(ge=0.0, le=1.0, default=1.0)
    symbol_resolution: float = Field(ge=0.0, le=1.0, default=1.0)


class FallbackProvenance(BaseModel):
    """When a resolved entity used fallback/alternative extraction."""

    strategy: str
    reason: str = ""
    original_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ResolvedBlock(BaseModel):
    """A semantic block with evidence traceability."""

    block_id: str
    block_type: BlockType
    region_id: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    symbol_refs: list[ResolvedSymbolRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    fallback: FallbackProvenance | None = None


class ResolvedPageV1(BaseModel):
    """Semantic resolution of a page, referencing evidence entities."""

    schema_version: str = Field(
        default="resolved_page.v1",
        pattern=r"^resolved_page\.v\d+$",
    )
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    source_evidence_hash: str = ""
    regions: list[ResolvedRegion] = Field(default_factory=list)
    blocks: list[ResolvedBlock] = Field(default_factory=list)
    main_flow_order: list[str] = Field(
        default_factory=list,
        description="Region or block IDs in main-flow reading order",
    )
    anchor_edges: list[AnchorEdge] = Field(default_factory=list)
    symbol_refs: list[ResolvedSymbolRef] = Field(default_factory=list)
    confidence: SemanticConfidence | None = None
    provenance: ProvenanceRef | None = None

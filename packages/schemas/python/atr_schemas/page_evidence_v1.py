"""PageEvidenceV1 — raw page evidence without semantic interpretation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import PageDimensions
from atr_schemas.evidence_primitives_v1 import EvidenceEntity


class EvidenceTransformMeta(BaseModel):
    """Provenance and transform metadata for the evidence layer."""

    source_native_hash: str = ""
    source_layout_hash: str = ""
    extractor: str = ""
    extractor_version: str = ""
    extraction_timestamp: str = ""
    coordinate_space: str = Field(default="pdf_points", description="Base coordinate system")
    page_dimensions_pt: PageDimensions


class PageEvidenceV1(BaseModel):
    """Raw page evidence — all observed entities without semantic interpretation."""

    schema_version: str = Field(
        default="page_evidence.v1",
        pattern=r"^page_evidence\.v\d+$",
    )
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    transform: EvidenceTransformMeta
    entities: list[EvidenceEntity] = Field(default_factory=list)

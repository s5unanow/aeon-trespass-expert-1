"""RuleChunkV1 — semantic rule chunk derived from PageIRV1 for assistant retrieval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import NormRect
from atr_schemas.enums import LanguageCode


class GlossaryConcept(BaseModel):
    """A glossary concept referenced within a rule chunk."""

    concept_id: str
    surface_form: str = ""


class RuleChunkV1(BaseModel):
    """Semantic rule chunk anchored to canonical IR for assistant retrieval.

    Each chunk represents one answerable unit of rule text derived from
    PageIRV1 blocks, with bilingual text payloads tied to the same
    canonical anchor.
    """

    schema_version: str = Field(default="rule_chunk.v1", pattern=r"^rule_chunk\.v\d+$")
    rule_chunk_id: str
    document_id: str
    edition: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    source_page_number: int = Field(ge=1)
    section_path: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    canonical_anchor_id: str
    language: LanguageCode
    text: str
    normalized_text: str = ""
    glossary_concepts: list[GlossaryConcept] = Field(default_factory=list)
    symbol_ids: list[str] = Field(default_factory=list)
    deep_link: str = ""
    facsimile_bbox_refs: list[NormRect] = Field(default_factory=list)

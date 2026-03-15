"""TranslationResultV1 — structured translation response contract."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.page_ir_v1 import InlineNode


class ConceptRealization(BaseModel):
    """How a concept was realized in the target language."""

    concept_id: str
    surface_form: str


class TranslatedSegment(BaseModel):
    """A single translated block."""

    segment_id: str
    target_inline: list[InlineNode] = Field(default_factory=list)
    concept_realizations: list[ConceptRealization] = Field(default_factory=list)


class TranslationResultV1(BaseModel):
    """Structured translation response."""

    schema_version: str = Field(
        default="translation_result.v1", pattern=r"^translation_result\.v\d+$"
    )
    batch_id: str
    segments: list[TranslatedSegment] = Field(default_factory=list)

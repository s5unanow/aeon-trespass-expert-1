"""TranslationBatchV1 — structured translation request contract."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.page_ir_v1 import InlineNode


class SegmentContext(BaseModel):
    """Contextual information for a translation segment.

    S5U-734 — table-cell segments additionally carry ``parent_block_id``,
    ``row_index``, ``cell_index``, ``is_header_row`` and ``is_header_cell``
    so the downstream re-materializer can stitch translated cells back into
    ``TableRowBlock`` / ``TableCellBlock`` structure. Non-table segments
    leave these fields at their defaults.
    """

    page_id: str = ""
    section_path: list[str] = Field(default_factory=list)
    prev_heading: str = ""
    # S5U-734 table-cell fields
    parent_block_id: str = ""
    row_index: int | None = None
    cell_index: int | None = None
    is_header_row: bool = False
    is_header_cell: bool = False


class TranslationSegment(BaseModel):
    """A single block to translate."""

    segment_id: str
    block_type: str = ""
    source_inline: list[InlineNode] = Field(default_factory=list)
    context: SegmentContext = Field(default_factory=SegmentContext)
    required_concepts: list[str] = Field(default_factory=list)
    forbidden_targets: list[str] = Field(default_factory=list)
    locked_nodes: list[str] = Field(default_factory=list)
    source_checksum: str = ""


class TranslationBatchV1(BaseModel):
    """Structured translation request."""

    schema_version: str = Field(
        default="translation_batch.v1", pattern=r"^translation_batch\.v\d+$"
    )
    batch_id: str
    source_lang: str = "en"
    target_lang: str = "ru"
    prompt_profile: str = ""
    segments: list[TranslationSegment] = Field(default_factory=list)

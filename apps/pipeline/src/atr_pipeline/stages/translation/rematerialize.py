"""Rebuild RU ``PageIRV1.blocks`` from EN source IR + translation result.

Extracted from ``stage.py`` (S5U-1228) to keep that file under the 400-line
cap after the per-page resume orchestration was added. Pure transformation
logic — no I/O, no LLM calls — so it carries no stage ``version`` semantics of
its own; behavioral changes here still require the ``TranslationStage.version``
bump per ``.claude/rules/pipeline.md`` because they alter the persisted
``page_ir.v1.ru`` shape.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    TableChild,
    TableRowBlock,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1

_BLOCK_TYPE_MAP: dict[str, type[BaseModel]] = {
    "heading": HeadingBlock,
    "paragraph": ParagraphBlock,
    "list": ListBlock,
    "list_item": ListItemBlock,
    "table": TableBlock,
    "callout": CalloutBlock,
    "figure": FigureBlock,
    "caption": CaptionBlock,
}

# Structural metadata fields to copy from source block (beyond block_id + children).
_STRUCTURAL_FIELDS: dict[str, list[str]] = {
    "heading": ["level"],
    "list": ["ordered"],
    "callout": ["variant"],
    "figure": ["asset_id"],
}


def _translated_by_id(result: TranslationResultV1) -> dict[str, TranslatedSegment]:
    """Index translated segments by their ``segment_id``."""
    return {seg.segment_id: seg for seg in result.segments}


def _batch_seg_by_id(batch: TranslationBatchV1) -> dict[str, TranslationSegment]:
    """Index batch segments by their ``segment_id``."""
    return {seg.segment_id: seg for seg in batch.segments}


def _rebuild_structured_table(
    src_block: TableBlock,
    *,
    batch_by_id: dict[str, TranslationSegment],
    translated_by_id: dict[str, TranslatedSegment],
) -> TableBlock:
    """S5U-734 — reassemble a structured RU ``TableBlock`` from per-cell segments.

    Preserves the EN row/cell structure (block ids, header flags, row ordering).
    Missing translations leave the cell structurally present with empty
    ``children`` rather than collapsing the row.
    """
    new_rows: list[TableChild] = []
    for row in src_block.children:
        if not isinstance(row, TableRowBlock):
            # Legacy mixed-content child; pass through unchanged. The
            # planner skipped these, so there is no translation to apply.
            new_rows.append(row)
            continue
        new_cells: list[TableCellBlock] = []
        for cell in row.cells:
            translated = translated_by_id.get(cell.block_id)
            target_inline: list[InlineNode] = (
                list(translated.target_inline) if translated is not None else []
            )
            new_cells.append(
                TableCellBlock(
                    block_id=cell.block_id,
                    bbox=cell.bbox,
                    header=cell.header,
                    children=target_inline,
                    translatable=cell.translatable,
                    source_ref=cell.source_ref,
                )
            )
        new_rows.append(
            TableRowBlock(
                block_id=row.block_id,
                bbox=row.bbox,
                header=row.header,
                cells=new_cells,
                translatable=row.translatable,
                source_ref=row.source_ref,
            )
        )
    # Silence unused-variable warnings from the batch index — the source of
    # truth for structure is the EN source block; the batch mapping is
    # retained for future use (e.g., untranslatable-cell policy).
    _ = batch_by_id
    return TableBlock(
        block_id=src_block.block_id,
        bbox=src_block.bbox,
        children=new_rows,
        translatable=src_block.translatable,
        source_ref=src_block.source_ref,
    )


def rematerialize_ru_blocks(
    en_ir: PageIRV1,
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> list[Block]:
    """Rebuild the RU ``PageIRV1.blocks`` from the EN source IR and the
    translation result. Structured tables are reassembled per S5U-734; other
    blocks retain their prior single-segment re-materialization path.
    """
    translated_by_id = _translated_by_id(result)
    batch_by_id = _batch_seg_by_id(batch)

    ru_blocks: list[Block] = []
    for src_block in en_ir.blocks:
        # Structured TableBlock — per-cell re-assembly.
        if isinstance(src_block, TableBlock) and any(
            isinstance(c, TableRowBlock) for c in src_block.children
        ):
            ru_blocks.append(
                _rebuild_structured_table(
                    src_block,
                    batch_by_id=batch_by_id,
                    translated_by_id=translated_by_id,
                )
            )
            continue

        # Non-table or legacy flat table — use the top-level segment.
        translated = translated_by_id.get(src_block.block_id)
        if translated is None:
            continue

        block_cls = _BLOCK_TYPE_MAP.get(src_block.type, ParagraphBlock)
        kwargs: dict[str, object] = {
            "block_id": src_block.block_id,
            "children": list(translated.target_inline),
            "bbox": src_block.bbox,
        }
        for field in _STRUCTURAL_FIELDS.get(src_block.type, []):
            kwargs[field] = getattr(src_block, field)
        ru_blocks.append(cast(Block, block_cls(**kwargs)))

    return ru_blocks

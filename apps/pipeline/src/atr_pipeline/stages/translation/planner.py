"""Translation planner — convert source PageIRV1 blocks to TranslationBatchV1."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def build_translation_batch(page_ir: PageIRV1) -> TranslationBatchV1:
    """Build a translation batch from an English PageIRV1."""
    segments: list[TranslationSegment] = []
    prev_heading = ""

    for block in page_ir.blocks:
        if not getattr(block, "translatable", False):
            continue

        segment = TranslationSegment(
            segment_id=block.block_id,
            block_type=block.type,
            source_inline=list(block.children),
            context=SegmentContext(
                page_id=page_ir.page_id,
                prev_heading=prev_heading,
            ),
        )

        # Track locked icon nodes
        for child in block.children:
            if child.type == "icon":
                segment.locked_nodes.append(child.symbol_id)  # type: ignore[union-attr]
                segment.required_concepts.append(
                    f"concept.{child.symbol_id.removeprefix('sym.')}"  # type: ignore[union-attr]
                )

        segments.append(segment)

        if isinstance(block, HeadingBlock):
            heading_texts = [c.text for c in block.children if c.type == "text"]  # type: ignore[union-attr]
            prev_heading = " ".join(heading_texts)

    return TranslationBatchV1(
        batch_id=f"tr.{page_ir.page_id}.01",
        source_lang=page_ir.language.value,
        target_lang="ru",
        segments=segments,
    )

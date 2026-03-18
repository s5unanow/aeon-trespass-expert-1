"""Translation planner — convert source PageIRV1 blocks to TranslationBatchV1."""

from __future__ import annotations

import re

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.page_ir_v1 import (
    DividerBlock,
    HeadingBlock,
    IconInline,
    PageIRV1,
    UnknownBlock,
)
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def build_translation_batch(
    page_ir: PageIRV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslationBatchV1:
    """Build a translation batch from an English PageIRV1.

    When *concept_registry* is provided, each segment is enriched with
    ``required_concepts`` and ``forbidden_targets`` for every concept
    whose source pattern appears in the segment text.
    """
    # Pre-build concept lookup structures
    _concept_patterns: list[tuple[re.Pattern[str], str, list[str]]] = []
    _icon_forbidden: dict[str, list[str]] = {}  # symbol_id -> forbidden

    if concept_registry:
        for c in concept_registry.concepts:
            # Build regex from source patterns / lemma
            patterns = c.source.patterns or [c.source.lemma]
            for pat in patterns:
                rx = re.compile(re.escape(pat), re.IGNORECASE)
                _concept_patterns.append((rx, c.concept_id, c.forbidden_targets))
            if c.icon_binding:
                _icon_forbidden[c.icon_binding] = c.forbidden_targets

    segments: list[TranslationSegment] = []
    prev_heading = ""

    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
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
            if isinstance(child, IconInline):
                sid = child.symbol_id
                segment.locked_nodes.append(sid)
                segment.required_concepts.append(f"concept.{sid.removeprefix('sym.')}")
                # Add forbidden targets from icon-bound concepts
                if sid in _icon_forbidden:
                    for ft in _icon_forbidden[sid]:
                        if ft not in segment.forbidden_targets:
                            segment.forbidden_targets.append(ft)

        # Scan text for concept pattern matches
        if _concept_patterns:
            full_text = " ".join(
                child.text
                for child in block.children
                if child.type == "text" and hasattr(child, "text")
            )
            for rx, concept_id, forbidden in _concept_patterns:
                if rx.search(full_text):
                    if concept_id not in segment.required_concepts:
                        segment.required_concepts.append(concept_id)
                    for ft in forbidden:
                        if ft not in segment.forbidden_targets:
                            segment.forbidden_targets.append(ft)

        segments.append(segment)

        if isinstance(block, HeadingBlock):
            heading_texts = [
                c.text for c in block.children if c.type == "text" and hasattr(c, "text")
            ]
            prev_heading = " ".join(heading_texts)

    return TranslationBatchV1(
        batch_id=f"tr.{page_ir.page_id}.01",
        source_lang=page_ir.language.value,
        target_lang="ru",
        segments=segments,
    )

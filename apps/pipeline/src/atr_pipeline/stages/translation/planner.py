"""Translation planner — convert source PageIRV1 blocks to TranslationBatchV1."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from atr_pipeline.stages.translation.grouping import GROUP_MARKER_PREFIX
from atr_pipeline.utils.hashing import sha256_str
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableRowBlock,
    UnknownBlock,
    XrefInline,
)
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)

_ConceptRule = tuple[re.Pattern[str], str, list[str]]

_NARRATIVE_GROUP_BLOCK_TYPES = (
    HeadingBlock,
    ParagraphBlock,
    ListBlock,
    ListItemBlock,
    CalloutBlock,
    CaptionBlock,
)
_MAX_NARRATIVE_GROUP_BLOCKS = 8
_MAX_NARRATIVE_GROUP_CHARS = 4500


def _inline_checksum(nodes: Sequence[object]) -> str:
    """Compute a short hash of serialized inline nodes for cache invalidation."""
    canonical = json.dumps(
        [n.model_dump(mode="json") if hasattr(n, "model_dump") else n for n in nodes],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256_str(canonical)[:12]


def _build_concept_indices(
    registry: ConceptRegistryV1 | None,
) -> tuple[list[_ConceptRule], dict[str, list[str]]]:
    """Return (text-pattern rules, icon-binding -> forbidden targets)."""
    patterns: list[_ConceptRule] = []
    icon_forbidden: dict[str, list[str]] = {}
    if registry is None:
        return patterns, icon_forbidden
    for c in registry.concepts:
        source_patterns = c.source.patterns or [c.source.lemma]
        for pat in source_patterns:
            rx = re.compile(re.escape(pat), re.IGNORECASE)
            patterns.append((rx, c.concept_id, c.forbidden_targets))
        if c.icon_binding:
            icon_forbidden[c.icon_binding] = c.forbidden_targets
    return patterns, icon_forbidden


def _apply_concepts(
    segment: TranslationSegment,
    *,
    source_inline: list[InlineNode],
    patterns: list[_ConceptRule],
    icon_forbidden: dict[str, list[str]],
) -> None:
    """Populate concept constraints on ``segment`` from inline content."""
    for child in source_inline:
        if isinstance(child, IconInline):
            sid = child.symbol_id
            segment.locked_nodes.append(sid)
            segment.required_concepts.append(f"concept.{sid.removeprefix('sym.')}")
            if sid in icon_forbidden:
                for ft in icon_forbidden[sid]:
                    if ft not in segment.forbidden_targets:
                        segment.forbidden_targets.append(ft)

    if not patterns:
        return

    full_text = " ".join(
        child.text for child in source_inline if child.type == "text" and hasattr(child, "text")
    )
    for rx, concept_id, forbidden in patterns:
        if rx.search(full_text):
            if concept_id not in segment.required_concepts:
                segment.required_concepts.append(concept_id)
            for ft in forbidden:
                if ft not in segment.forbidden_targets:
                    segment.forbidden_targets.append(ft)


def _emit_table_cell_segments(
    block: TableBlock,
    *,
    page_id: str,
    prev_heading: str,
    patterns: list[_ConceptRule],
    icon_forbidden: dict[str, list[str]],
) -> list[TranslationSegment]:
    """S5U-734 — emit one ``TranslationSegment`` per ``TableCellBlock``.

    Row-level context (row_index, is_header_row, parent_block_id) and
    cell-level context (cell_index, is_header_cell) travel in
    ``SegmentContext`` so the re-materializer can group cells back into
    ``TableRowBlock`` rows. Non-row children (legacy flat inlines) are
    skipped here — ``_table_is_structured`` ensures callers only dispatch
    to this branch when at least one ``TableRowBlock`` child exists.
    """
    segments: list[TranslationSegment] = []
    row_index = 0
    for row in block.children:
        if not isinstance(row, TableRowBlock):
            # Legacy mixed content: skip flat inlines under a structured table.
            continue
        if not row.translatable:
            row_index += 1
            continue
        for cell_index, cell in enumerate(row.cells):
            if not cell.translatable:
                continue
            source_inline = list(cell.children)
            segment = TranslationSegment(
                segment_id=cell.block_id,
                block_type="table_cell",
                source_inline=source_inline,
                source_checksum=_inline_checksum(source_inline),
                context=SegmentContext(
                    page_id=page_id,
                    prev_heading=prev_heading,
                    parent_block_id=block.block_id,
                    row_index=row_index,
                    cell_index=cell_index,
                    is_header_row=row.header,
                    is_header_cell=cell.header,
                ),
            )
            _apply_concepts(
                segment,
                source_inline=source_inline,
                patterns=patterns,
                icon_forbidden=icon_forbidden,
            )
            segments.append(segment)
        row_index += 1
    return segments


def _table_is_structured(block: TableBlock) -> bool:
    """True iff at least one child is a ``TableRowBlock``."""
    return any(isinstance(c, TableRowBlock) for c in block.children)


def _emit_block_segment(
    block: object,
    *,
    page_id: str,
    prev_heading: str,
    patterns: list[_ConceptRule],
    icon_forbidden: dict[str, list[str]],
) -> TranslationSegment:
    """Emit a single segment for a non-table (or legacy flat table) block."""
    source_inline: list[InlineNode] = list(getattr(block, "children", []))
    segment = TranslationSegment(
        segment_id=getattr(block, "block_id", ""),
        block_type=getattr(block, "type", ""),
        source_inline=source_inline,
        source_checksum=_inline_checksum(source_inline),
        context=SegmentContext(
            page_id=page_id,
            prev_heading=prev_heading,
        ),
    )
    _apply_concepts(
        segment,
        source_inline=source_inline,
        patterns=patterns,
        icon_forbidden=icon_forbidden,
    )
    return segment


def _is_narrative_group_candidate(block: Block) -> bool:
    """True when *block* should be translated as part of a larger prose unit."""
    return isinstance(block, _NARRATIVE_GROUP_BLOCK_TYPES)


def _block_text(block: object) -> str:
    """Return plain text for source-context fields."""
    children = getattr(block, "children", [])
    if not isinstance(children, list):
        return ""
    return "".join(c.text for c in children if c.type == "text" and hasattr(c, "text"))


def _group_text_len(blocks: list[Block]) -> int:
    """Approximate prompt-visible text size for group capping."""
    return sum(len(_block_text(block)) for block in blocks)


def _block_marker(block: object) -> XrefInline:
    """Boundary marker copied through narrative-group translation."""
    block_id = getattr(block, "block_id", "")
    block_type = getattr(block, "type", "")
    return XrefInline(
        target_section_id=f"{GROUP_MARKER_PREFIX}{block_id}",
        label=block_type,
    )


def _emit_narrative_group_segment(
    blocks: list[Block],
    *,
    page_id: str,
    prev_heading: str,
    group_index: int,
    patterns: list[_ConceptRule],
    icon_forbidden: dict[str, list[str]],
) -> TranslationSegment:
    """Emit one full-prose translation unit for contiguous narrative blocks.

    The group carries ``xref`` boundary markers before each source block. LLMs
    are already required to copy non-text nodes unchanged; the translation
    stage later splits the group output back into the original block IDs using
    these markers.
    """
    source_inline: list[InlineNode] = []
    section_path = [getattr(block, "block_id", "") for block in blocks]
    for block in blocks:
        source_inline.append(_block_marker(block))
        source_inline.extend(list(getattr(block, "children", [])))

    segment = TranslationSegment(
        segment_id=f"group.{page_id}.{group_index:03d}",
        block_type="narrative_group",
        source_inline=source_inline,
        source_checksum=_inline_checksum(source_inline),
        context=SegmentContext(
            page_id=page_id,
            prev_heading=prev_heading,
            section_path=section_path,
        ),
    )
    _apply_concepts(
        segment,
        source_inline=source_inline,
        patterns=patterns,
        icon_forbidden=icon_forbidden,
    )
    return segment


def build_translation_batch(
    page_ir: PageIRV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
    prompt_profile: str = "",
) -> TranslationBatchV1:
    """Build a translation batch from an English PageIRV1.

    When *concept_registry* is provided, each segment is enriched with
    ``required_concepts`` and ``forbidden_targets`` for every concept
    whose source pattern appears in the segment text.

    S5U-734 — structured ``TableBlock`` children (``TableRowBlock`` with
    ``TableCellBlock`` cells) emit one segment per cell rather than one
    segment per table; this is what lets the re-materializer preserve
    row/cell boundaries in the RU output. Legacy flat ``TableBlock``
    children fall back to a single table-level segment for back-compat.
    """
    patterns, icon_forbidden = _build_concept_indices(concept_registry)

    segments: list[TranslationSegment] = []
    prev_heading = ""
    narrative_group: list[Block] = []
    narrative_group_index = 1

    def flush_narrative_group() -> None:
        nonlocal narrative_group, narrative_group_index
        if not narrative_group:
            return
        if len(narrative_group) == 1:
            segments.append(
                _emit_block_segment(
                    narrative_group[0],
                    page_id=page_ir.page_id,
                    prev_heading=prev_heading,
                    patterns=patterns,
                    icon_forbidden=icon_forbidden,
                )
            )
        else:
            segments.append(
                _emit_narrative_group_segment(
                    narrative_group,
                    page_id=page_ir.page_id,
                    prev_heading=prev_heading,
                    group_index=narrative_group_index,
                    patterns=patterns,
                    icon_forbidden=icon_forbidden,
                )
            )
            narrative_group_index += 1
        narrative_group = []

    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            flush_narrative_group()
            continue
        if not getattr(block, "translatable", False):
            flush_narrative_group()
            continue

        if isinstance(block, TableBlock) and _table_is_structured(block):
            flush_narrative_group()
            segments.extend(
                _emit_table_cell_segments(
                    block,
                    page_id=page_ir.page_id,
                    prev_heading=prev_heading,
                    patterns=patterns,
                    icon_forbidden=icon_forbidden,
                )
            )
            continue

        if isinstance(block, (FigureBlock, TableBlock)):
            flush_narrative_group()
            segments.append(
                _emit_block_segment(
                    block,
                    page_id=page_ir.page_id,
                    prev_heading=prev_heading,
                    patterns=patterns,
                    icon_forbidden=icon_forbidden,
                )
            )
            continue

        if _is_narrative_group_candidate(block):
            should_flush = narrative_group and (
                isinstance(block, HeadingBlock)
                or len(narrative_group) >= _MAX_NARRATIVE_GROUP_BLOCKS
                or _group_text_len(narrative_group) + len(_block_text(block))
                > _MAX_NARRATIVE_GROUP_CHARS
            )
            if should_flush:
                flush_narrative_group()
            narrative_group.append(block)
            if isinstance(block, HeadingBlock):
                heading_text = _block_text(block)
                if heading_text:
                    prev_heading = heading_text
            continue

        segments.append(
            _emit_block_segment(
                block,
                page_id=page_ir.page_id,
                prev_heading=prev_heading,
                patterns=patterns,
                icon_forbidden=icon_forbidden,
            )
        )

        if isinstance(block, HeadingBlock):
            heading_texts = [
                c.text for c in block.children if c.type == "text" and hasattr(c, "text")
            ]
            prev_heading = " ".join(heading_texts)

    flush_narrative_group()

    return TranslationBatchV1(
        batch_id=f"tr.{page_ir.page_id}.01",
        source_lang=page_ir.language.value,
        target_lang="ru",
        prompt_profile=prompt_profile,
        segments=segments,
    )

"""Helpers for narrative-group translation segments."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import InlineNode, LineBreakInline, TextInline, XrefInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment
from atr_schemas.translation_result_v1 import (
    ConceptRealization,
    TranslatedSegment,
    TranslationResultV1,
)

GROUP_MARKER_PREFIX = "translation-block:"


def is_group_marker(node: InlineNode) -> bool:
    """True when *node* is a narrative-group block-boundary marker."""
    return isinstance(node, XrefInline) and node.target_section_id.startswith(GROUP_MARKER_PREFIX)


def group_marker_block_id(node: XrefInline) -> str:
    """Return the original block id encoded in a group marker."""
    return node.target_section_id.removeprefix(GROUP_MARKER_PREFIX)


def group_marker_ids(nodes: list[InlineNode]) -> list[str]:
    """Return narrative-group marker ids in encounter order."""
    return [
        group_marker_block_id(node)
        for node in nodes
        if isinstance(node, XrefInline) and is_group_marker(node)
    ]


def text_before_first_group_marker(nodes: list[InlineNode]) -> str:
    """Return translated text that appears before the first group marker."""
    parts: list[str] = []
    for node in nodes:
        if is_group_marker(node):
            break
        if isinstance(node, TextInline):
            parts.append(node.text)
    return "".join(parts).strip()


def _trim_boundary_breaks(nodes: list[InlineNode]) -> list[InlineNode]:
    """Remove boundary-only line breaks from the start/end of a split block."""
    start = 0
    end = len(nodes)
    while start < end and isinstance(nodes[start], LineBreakInline):
        start += 1
    while end > start and isinstance(nodes[end - 1], LineBreakInline):
        end -= 1
    return nodes[start:end]


def split_group_source_segments(segment: TranslationSegment) -> list[TranslationSegment]:
    """Expand one narrative-group source segment into original block segments."""
    expanded: list[TranslationSegment] = []
    current_block_id = ""
    current_block_type = "paragraph"
    current_inline: list[InlineNode] = []

    def flush_current() -> None:
        if not current_block_id:
            return
        expanded.append(
            TranslationSegment(
                segment_id=current_block_id,
                block_type=current_block_type,
                source_inline=_trim_boundary_breaks(list(current_inline)),
                source_checksum=segment.source_checksum,
                context=segment.context,
                required_concepts=list(segment.required_concepts),
                forbidden_targets=list(segment.forbidden_targets),
                locked_nodes=list(segment.locked_nodes),
            )
        )

    for node in segment.source_inline:
        if isinstance(node, XrefInline) and is_group_marker(node):
            flush_current()
            current_block_id = group_marker_block_id(node)
            current_block_type = node.label or "paragraph"
            current_inline = []
            continue
        if current_block_id:
            current_inline.append(node)
    flush_current()
    return expanded


def split_group_target_inline(nodes: list[InlineNode]) -> dict[str, list[InlineNode]]:
    """Split a translated narrative group by copied block-boundary markers."""
    split: dict[str, list[InlineNode]] = {}
    current_block_id = ""
    for node in nodes:
        if isinstance(node, XrefInline) and is_group_marker(node):
            current_block_id = group_marker_block_id(node)
            split.setdefault(current_block_id, [])
            continue
        if current_block_id:
            split[current_block_id].append(node)
    return {block_id: _trim_boundary_breaks(inline) for block_id, inline in split.items()}


def _matched_realizations_for_block(
    inline: list[InlineNode],
    realizations: list[ConceptRealization],
) -> list[ConceptRealization]:
    """Return group-level concept realizations whose surface appears in a block."""
    target_text = " ".join(node.text for node in inline if isinstance(node, TextInline))
    return [cr for cr in realizations if cr.surface_form and cr.surface_form in target_text]


def expand_grouped_batch(batch: TranslationBatchV1) -> TranslationBatchV1:
    """Return a block-addressable batch for validation/rematerialization."""
    expanded_segments: list[TranslationSegment] = []
    for segment in batch.segments:
        if segment.block_type == "narrative_group":
            expanded_segments.extend(split_group_source_segments(segment))
        else:
            expanded_segments.append(segment)
    return TranslationBatchV1(
        batch_id=batch.batch_id,
        source_lang=batch.source_lang,
        target_lang=batch.target_lang,
        prompt_profile=batch.prompt_profile,
        segments=expanded_segments,
    )


def expand_grouped_result(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> TranslationResultV1:
    """Return a block-addressable result by splitting narrative-group outputs."""
    batch_by_id = {s.segment_id: s for s in batch.segments}
    expanded_segments: list[TranslatedSegment] = []

    for translated in result.segments:
        source = batch_by_id.get(translated.segment_id)
        if source is None or source.block_type != "narrative_group":
            expanded_segments.append(translated)
            continue

        split = split_group_target_inline(list(translated.target_inline))
        unmatched_realizations = list(translated.concept_realizations or [])
        source_blocks = split_group_source_segments(source)
        for index, source_block in enumerate(source_blocks):
            target_inline = split.get(source_block.segment_id, [])
            concept_realizations = _matched_realizations_for_block(
                target_inline,
                unmatched_realizations,
            )
            for matched in concept_realizations:
                if matched in unmatched_realizations:
                    unmatched_realizations.remove(matched)
            if index == 0 and unmatched_realizations:
                concept_realizations.extend(unmatched_realizations)
                unmatched_realizations = []
            expanded_segments.append(
                TranslatedSegment(
                    segment_id=source_block.segment_id,
                    target_inline=target_inline,
                    concept_realizations=concept_realizations,
                )
            )

    return TranslationResultV1(
        batch_id=result.batch_id,
        segments=expanded_segments,
    )

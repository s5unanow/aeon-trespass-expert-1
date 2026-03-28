"""Block post-processing utilities extracted from real_block_builder.

Contains paragraph splitting and deduplication logic that runs after
initial block construction.
"""

from __future__ import annotations

import re

from atr_schemas.common import Rect
from atr_schemas.page_ir_v1 import InlineNode, ListItemBlock, ParagraphBlock, TextInline

# Sentence boundary: ". " followed by uppercase Latin or Cyrillic letter.
SENTENCE_BOUNDARY_RE = re.compile(r"\. (?=[A-ZА-ЯЁ])")  # noqa: RUF001


def _split_children_at(
    children: list[InlineNode],
    split_pos: int,
    offset_map: list[tuple[int, int]],
) -> tuple[list[InlineNode], list[InlineNode]]:
    """Split a children list at the given character offset."""
    child_idx, pos_in_child = offset_map[split_pos - 1]
    first: list[InlineNode] = []
    second: list[InlineNode] = []

    for ci, child in enumerate(children):
        if ci < child_idx:
            first.append(child)
        elif ci == child_idx and isinstance(child, TextInline):
            cut = pos_in_child + 1
            left_text = child.text[:cut]
            right_text = child.text[cut:]
            if left_text:
                first.append(TextInline(text=left_text, marks=child.marks, lang=child.lang))
            if right_text:
                second.append(TextInline(text=right_text, marks=child.marks, lang=child.lang))
        elif ci == child_idx:
            second.append(child)
        else:
            second.append(child)

    return first, second


def _build_offset_map(children: list[InlineNode]) -> list[tuple[int, int]]:
    """Build a mapping of character offset -> (child_index, char_within_child)."""
    offset_map: list[tuple[int, int]] = []
    for ci, child in enumerate(children):
        if hasattr(child, "text"):
            for pos in range(len(child.text)):
                offset_map.append((ci, pos))
    return offset_map


def _find_sentence_split(text: str, max_chars: int) -> int:
    """Find the last sentence boundary before max_chars. Returns -1 if none."""
    accumulated = text[:max_chars]
    split_pos = -1
    for m in SENTENCE_BOUNDARY_RE.finditer(accumulated):
        split_pos = m.start() + 2
    return split_pos


def split_long_paragraphs(
    blocks: list[object],
    max_chars: int = 600,
) -> list[object]:
    """Split paragraph blocks whose text exceeds *max_chars* at sentence boundaries."""
    result: list[object] = []
    for block in blocks:
        if not isinstance(block, ParagraphBlock):
            result.append(block)
            continue

        total_text = "".join(c.text for c in block.children if hasattr(c, "text"))
        if len(total_text) <= max_chars:
            result.append(block)
            continue

        remaining_children: list[InlineNode] = list(block.children)
        base_id = block.block_id
        part = 0

        while remaining_children:
            remaining_text = "".join(c.text for c in remaining_children if hasattr(c, "text"))
            if len(remaining_text) <= max_chars:
                part_id = f"{base_id}.{part}" if part > 0 else base_id
                result.append(
                    ParagraphBlock(block_id=part_id, bbox=block.bbox, children=remaining_children)
                )
                break

            offset_map = _build_offset_map(remaining_children)
            split_pos = _find_sentence_split(remaining_text, max_chars)

            if split_pos <= 0:
                part_id = f"{base_id}.{part}" if part > 0 else base_id
                result.append(
                    ParagraphBlock(block_id=part_id, bbox=block.bbox, children=remaining_children)
                )
                break

            first_children, second_children = _split_children_at(
                remaining_children,
                split_pos,
                offset_map,
            )

            part_id = f"{base_id}.{part}" if part > 0 else base_id
            if first_children:
                result.append(
                    ParagraphBlock(block_id=part_id, bbox=block.bbox, children=first_children)
                )
            part += 1
            remaining_children = second_children

    return result


def deduplicate_blocks(blocks: list[object]) -> list[object]:
    """Remove consecutive blocks with identical text content (first 80 chars)."""
    if not blocks:
        return blocks

    def _block_text_key(block: object) -> str:
        children = getattr(block, "children", [])
        text = "".join(c.text for c in children if hasattr(c, "text"))
        return text[:80]

    result: list[object] = [blocks[0]]
    for block in blocks[1:]:
        prev_key = _block_text_key(result[-1])
        curr_key = _block_text_key(block)
        if prev_key and prev_key == curr_key:
            continue
        result.append(block)
    return result


# ---------------------------------------------------------------------------
# List-item continuation merging
# ---------------------------------------------------------------------------

# Maximum vertical gap (pt) between a list item and its continuation paragraph.
_CONTINUATION_Y_GAP_MAX = 20.0


def _block_text(block: object) -> str:
    """Extract plain text from a block's children."""
    children = getattr(block, "children", [])
    return "".join(c.text for c in children if hasattr(c, "text"))


def _should_merge_continuation(item: ListItemBlock, para: ParagraphBlock) -> bool:
    """Return True when *para* looks like a continuation of *item*."""
    if not item.bbox or not para.bbox:
        return False
    y_gap = para.bbox.y0 - item.bbox.y1
    if y_gap > _CONTINUATION_Y_GAP_MAX or y_gap < -5.0:
        return False
    # Short-text list items (numbered steps like "1", "2.") always merge.
    if len(_block_text(item).strip()) <= 5:
        return True
    # Otherwise merge when the paragraph is indented at least as far.
    return para.bbox.x0 >= item.bbox.x0 - 5.0


def _merge_bbox(a: Rect | None, b: Rect | None) -> Rect | None:
    if a is None:
        return b
    if b is None:
        return a
    return Rect(
        x0=min(a.x0, b.x0),
        y0=min(a.y0, b.y0),
        x1=max(a.x1, b.x1),
        y1=max(a.y1, b.y1),
    )


def _merge_into_list_item(
    item: ListItemBlock,
    para: ParagraphBlock,
) -> ListItemBlock:
    """Merge *para* children into *item*, inserting a space separator."""
    merged: list[InlineNode] = list(item.children)
    if merged and para.children:
        last = merged[-1]
        if isinstance(last, TextInline) and last.text and not last.text[-1].isspace():
            merged[-1] = TextInline(text=last.text + " ", marks=last.marks, lang=last.lang)
    merged.extend(para.children)
    return ListItemBlock(
        block_id=item.block_id,
        bbox=_merge_bbox(item.bbox, para.bbox),
        children=merged,
    )


def merge_list_continuations(blocks: list[object]) -> list[object]:
    """Merge paragraphs that are continuations of a preceding list item.

    Handles two patterns:
    1. ListItemBlock with short numeric text + ParagraphBlock → merged.
    2. ListItemBlock (any) + ParagraphBlock at matching indentation → merged.
    """
    if len(blocks) < 2:
        return list(blocks)

    result: list[object] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        next_block = blocks[i + 1] if i + 1 < len(blocks) else None
        if (
            isinstance(block, ListItemBlock)
            and isinstance(next_block, ParagraphBlock)
            and _should_merge_continuation(block, next_block)
        ):
            result.append(_merge_into_list_item(block, next_block))
            i += 2
        else:
            result.append(block)
            i += 1
    return result

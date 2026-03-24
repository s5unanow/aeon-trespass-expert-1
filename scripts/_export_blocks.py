"""Block postprocessing helpers for export_to_web: split, deduplicate, strip icons."""

from __future__ import annotations

import re

_SENTENCE_RE = re.compile(r"(?<=\. )(?=[A-ZА-ЯЁ])")  # noqa: RUF001

DECORATIVE_PREFIXES = (
    "sym.board_tile",
    "sym.art_",
    "sym.terrain_",
    "sym.marker_",
    "sym.crown_",
    "sym.die_",
    "sym.titan_helmet",
)


def text_content(block: dict) -> str:
    """Extract concatenated text from a block's children."""
    return "".join(c.get("text", "") for c in block.get("children", []) if c.get("kind") == "text")


def postprocess_blocks(blocks: list[dict]) -> list[dict]:
    """Strip decorative icons, split long paragraphs, deduplicate."""
    result: list[dict] = []

    for block in blocks:
        if "children" in block:
            block["children"] = [
                c
                for c in block["children"]
                if not (
                    c.get("kind") == "icon"
                    and c.get("symbol_id", "").startswith(DECORATIVE_PREFIXES)
                )
            ]

        if block.get("kind") == "paragraph":
            text = text_content(block)
            if len(text) > 600:
                for part in _split_paragraph(block):
                    if not _is_duplicate(result, part):
                        result.append(part)
                continue

        if not _is_duplicate(result, block):
            result.append(block)

    return result


def _find_split_point(boundaries: list[int], max_chars: int) -> int | None:
    """Find the best sentence boundary to split at."""
    split_at = None
    for b in boundaries:
        if b <= max_chars:
            split_at = b
        else:
            break
    if split_at is None or split_at < 100:
        split_at = next((b for b in boundaries if b >= 100), None)
    return split_at


def _locate_split_child(children: list[dict], split_at: int) -> tuple[int | None, int | None]:
    """Find the child index and offset where text position falls."""
    char_count = 0
    for i, child in enumerate(children):
        if child.get("kind") != "text":
            continue
        child_text = child.get("text", "")
        if char_count + len(child_text) >= split_at:
            return i, split_at - char_count
        char_count += len(child_text)
    return None, None


def _split_paragraph(block: dict, max_chars: int = 600) -> list[dict]:
    """Split a paragraph block at sentence boundaries."""
    children = block.get("children", [])
    text = text_content(block)
    if len(text) <= max_chars:
        return [block]

    boundaries = [m.start() for m in _SENTENCE_RE.finditer(text)]
    if not boundaries:
        return [block]

    split_at = _find_split_point(boundaries, max_chars)
    if split_at is None:
        return [block]

    split_idx, split_offset = _locate_split_child(children, split_at)
    if split_idx is None:
        return [block]

    first_children = children[:split_idx]
    remainder_children = children[split_idx:]

    split_child = remainder_children[0]
    if split_child.get("kind") == "text" and split_offset:
        text1 = split_child["text"][:split_offset]
        text2 = split_child["text"][split_offset:]
        if text1.strip():
            first_children.append({**split_child, "text": text1})
        if text2.strip():
            remainder_children = [{**split_child, "text": text2}, *remainder_children[1:]]
        else:
            remainder_children = remainder_children[1:]

    block1 = {**block, "id": f"{block['id']}.0", "children": first_children}
    block2 = {**block, "id": f"{block['id']}.1", "children": remainder_children}

    result = [block1]
    if len(text_content(block2)) > max_chars:
        result.extend(_split_paragraph(block2, max_chars))
    else:
        result.append(block2)
    return result


def _is_duplicate(blocks: list[dict], block: dict) -> bool:
    """Check if block duplicates any recent block (within last 5)."""
    this_text = text_content(block)[:80]
    if not this_text or len(this_text) < 3:
        return False
    for prev in blocks[-5:]:
        if prev.get("kind") != block.get("kind"):
            continue
        if text_content(prev)[:80] == this_text:
            return True
    return False

"""Build facsimile annotations from PageIRV1 blocks with bounding boxes."""

from __future__ import annotations

from typing import Literal

from atr_schemas.common import NormRect
from atr_schemas.page_ir_v1 import (
    Block,
    DividerBlock,
    IconInline,
    PageIRV1,
    UnknownBlock,
)
from atr_schemas.render_page_v1 import FacsimileAnnotation

AnnotationKind = Literal["title", "body", "caption", "callout", "label"]

# Block type → (annotation kind, base priority)
_BLOCK_KIND_MAP: dict[str, tuple[AnnotationKind, int]] = {
    "heading": ("title", 100),
    "callout": ("callout", 80),
    "caption": ("caption", 60),
    "paragraph": ("body", 40),
    "list_item": ("body", 40),
    "list": ("body", 40),
    "table": ("body", 30),
    "figure": ("label", 10),
}


def build_facsimile_annotations(
    en_ir: PageIRV1,
    ru_ir: PageIRV1 | None = None,
) -> list[FacsimileAnnotation]:
    """Convert PageIRV1 blocks to positioned facsimile annotations.

    Args:
        en_ir: English page IR (source of bboxes and original text).
        ru_ir: Russian page IR (source of translated text). May be ``None``
            for EN-only editions.

    Returns:
        Annotations sorted by descending priority.
    """
    dims = en_ir.dimensions_pt
    if dims is None or dims.width <= 0 or dims.height <= 0:
        return []

    # Index RU blocks by block_id for fast lookup
    ru_blocks: dict[str, Block] = {}
    if ru_ir is not None:
        for block in ru_ir.blocks:
            ru_blocks[block.block_id] = block

    annotations: list[FacsimileAnnotation] = []
    for block in en_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        if block.bbox is None:
            continue

        en_text = _extract_block_text(block)
        if not en_text.strip():
            continue

        kind, priority = _BLOCK_KIND_MAP.get(block.type, ("body", 20))

        ru_text = ""
        ru_block = ru_blocks.get(block.block_id)
        if ru_block is not None:
            ru_text = _extract_block_text(ru_block)

        bbox = NormRect(
            x0=max(0.0, min(1.0, block.bbox.x0 / dims.width)),
            y0=max(0.0, min(1.0, block.bbox.y0 / dims.height)),
            x1=max(0.0, min(1.0, block.bbox.x1 / dims.width)),
            y1=max(0.0, min(1.0, block.bbox.y1 / dims.height)),
        )

        annotations.append(
            FacsimileAnnotation(
                text=en_text,
                translated_text=ru_text,
                bbox=bbox,
                kind=kind,
                priority=priority,
            )
        )

    annotations.sort(key=lambda a: a.priority, reverse=True)
    return annotations


def _extract_block_text(block: Block) -> str:
    """Extract plain text from a block's inline children."""
    if isinstance(block, (DividerBlock, UnknownBlock)):
        return ""
    parts: list[str] = []
    for child in block.children:
        if child.type == "text":
            parts.append(child.text)
        elif isinstance(child, IconInline) and child.symbol_id:
            parts.append(f"[{child.symbol_id}]")
    return " ".join(parts)

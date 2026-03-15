"""Build RenderPageV1 from translated PageIRV1."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderIconInline,
    RenderInlineNode,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def build_render_page(page_ir: PageIRV1) -> RenderPageV1:
    """Map a translated PageIRV1 to a RenderPageV1 payload."""
    render_blocks = []
    block_refs = []
    title = ""

    for block in page_ir.blocks:
        block_refs.append(block.block_id)
        children = _convert_inline_nodes(block.children)

        if block.type == "heading":
            if not title:
                title = " ".join(
                    c.text for c in children if isinstance(c, RenderTextInline)
                )
            render_blocks.append(
                RenderHeadingBlock(
                    id=block.block_id,
                    level=block.level if isinstance(block, HeadingBlock) else 1,
                    children=children,
                )
            )
        elif block.type == "paragraph":
            render_blocks.append(
                RenderParagraphBlock(id=block.block_id, children=children)
            )

    return RenderPageV1(
        page=RenderPageMeta(
            id=page_ir.page_id,
            title=title,
            source_page_number=page_ir.page_number,
        ),
        blocks=render_blocks,  # type: ignore[arg-type]
        glossary_mentions=_extract_concept_mentions(page_ir),
        source_map=RenderSourceMap(
            page_id=page_ir.page_id,
            block_refs=block_refs,
        ),
    )


def _convert_inline_nodes(nodes: list[object]) -> list[RenderInlineNode]:  # type: ignore[type-arg]
    """Convert IR inline nodes to render inline nodes."""
    result: list[RenderInlineNode] = []  # type: ignore[type-arg]
    for node in nodes:
        if node.type == "text":  # type: ignore[union-attr]
            result.append(RenderTextInline(text=node.text))  # type: ignore[union-attr]
        elif node.type == "icon":  # type: ignore[union-attr]
            sym_id = node.symbol_id  # type: ignore[union-attr]
            alt = sym_id.removeprefix("sym.").capitalize()
            result.append(RenderIconInline(symbol_id=sym_id, alt=alt))
    return result


def _extract_concept_mentions(page_ir: PageIRV1) -> list[str]:
    """Extract concept mentions from block annotations."""
    mentions: list[str] = []
    for block in page_ir.blocks:
        for child in block.children:
            if child.type == "icon":  # type: ignore[union-attr]
                concept = f"concept.{child.symbol_id.removeprefix('sym.')}"  # type: ignore[union-attr]
                if concept not in mentions:
                    mentions.append(concept)
    return mentions

"""Build RenderPageV1 from translated PageIRV1."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import (
    DividerBlock,
    HeadingBlock,
    IconInline,
    InlineNode,
    PageIRV1,
    UnknownBlock,
)
from atr_schemas.render_page_v1 import (
    RenderBlock,
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
    render_blocks: list[RenderBlock] = []
    block_refs: list[str] = []
    title = ""

    for block in page_ir.blocks:
        block_refs.append(block.block_id)
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        children = _convert_inline_nodes(list(block.children))

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
        blocks=render_blocks,
        glossary_mentions=_extract_concept_mentions(page_ir),
        source_map=RenderSourceMap(
            page_id=page_ir.page_id,
            block_refs=block_refs,
        ),
    )


def _convert_inline_nodes(nodes: list[InlineNode]) -> list[RenderInlineNode]:
    """Convert IR inline nodes to render inline nodes."""
    result: list[RenderInlineNode] = []
    for node in nodes:
        if node.type == "text":
            result.append(RenderTextInline(text=node.text))
        elif node.type == "icon":
            assert isinstance(node, IconInline)
            sym_id = node.symbol_id
            alt = sym_id.removeprefix("sym.").capitalize()
            result.append(RenderIconInline(symbol_id=sym_id, alt=alt))
    return result


def _extract_concept_mentions(page_ir: PageIRV1) -> list[str]:
    """Extract concept mentions from block annotations."""
    mentions: list[str] = []
    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        for child in block.children:
            if isinstance(child, IconInline):
                concept = f"concept.{child.symbol_id.removeprefix('sym.')}"
                if concept not in mentions:
                    mentions.append(concept)
    return mentions

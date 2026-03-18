"""Build RenderPageV1 from translated PageIRV1."""

from __future__ import annotations

from atr_schemas.page_ir_v1 import (
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    InlineNode,
    PageIRV1,
    UnknownBlock,
)
from atr_schemas.render_page_v1 import (
    RenderBlock,
    RenderFigure,
    RenderFigureBlock,
    RenderHeadingBlock,
    RenderIconInline,
    RenderInlineNode,
    RenderListItemBlock,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def build_render_page(
    page_ir: PageIRV1,
    *,
    image_base_path: str = "",
) -> RenderPageV1:
    """Map a translated PageIRV1 to a RenderPageV1 payload.

    Args:
        page_ir: The page IR to convert.
        image_base_path: URL prefix for figure image ``src`` values.
            When empty, asset_id is used as-is.
    """
    render_blocks: list[RenderBlock] = []
    block_refs: list[str] = []
    figures: dict[str, RenderFigure] = {}
    title = ""

    for block in page_ir.blocks:
        block_refs.append(block.block_id)
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue

        # FigureBlock does not have translatable text children — handle separately
        if isinstance(block, FigureBlock):
            asset_id = block.asset_id
            render_blocks.append(
                RenderFigureBlock(
                    id=block.block_id,
                    asset_id=asset_id,
                    children=_convert_inline_nodes(list(block.children)),
                )
            )
            # Populate the figures lookup so the frontend can resolve src
            src = f"{image_base_path}/{asset_id}" if image_base_path else asset_id
            figures[asset_id] = RenderFigure(src=src, alt=asset_id)
            continue

        children = _convert_inline_nodes(list(block.children))

        if block.type == "heading":
            if not title:
                title = " ".join(c.text for c in children if isinstance(c, RenderTextInline))
            render_blocks.append(
                RenderHeadingBlock(
                    id=block.block_id,
                    level=block.level if isinstance(block, HeadingBlock) else 1,
                    children=children,
                )
            )
        elif block.type == "paragraph":
            render_blocks.append(RenderParagraphBlock(id=block.block_id, children=children))
        elif block.type == "list_item":
            render_blocks.append(RenderListItemBlock(id=block.block_id, children=children))

    return RenderPageV1(
        page=RenderPageMeta(
            id=page_ir.page_id,
            title=title,
            source_page_number=page_ir.page_number,
        ),
        blocks=render_blocks,
        figures=figures,
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
            marks = getattr(node, "marks", None) or []
            result.append(RenderTextInline(text=node.text, marks=marks))
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

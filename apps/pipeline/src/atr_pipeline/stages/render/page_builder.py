"""Build RenderPageV1 from translated PageIRV1."""

from __future__ import annotations

import re
from typing import assert_never

from atr_pipeline.stages.render.concept_matcher import (
    build_text_pattern_index,
    match_text_patterns,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    FigureRefInline,
    HeadingBlock,
    IconInline,
    InlineNode,
    LineBreakInline,
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableChild,
    TableRowBlock,
    TermMarkInline,
    TextInline,
    UnknownBlock,
    XrefInline,
    iter_table_inlines,
)
from atr_schemas.render_page_v1 import (
    RenderBlock,
    RenderCalloutBlock,
    RenderCaptionBlock,
    RenderFigure,
    RenderFigureBlock,
    RenderFigureRefInline,
    RenderHeadingBlock,
    RenderIconInline,
    RenderInlineNode,
    RenderListItemBlock,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTableBlock,
    RenderTableCellBlock,
    RenderTableChild,
    RenderTableRowBlock,
    RenderTextInline,
)

_LONE_MARKER_RE = re.compile(r"^\d+[\.\):]?\s*$")

# S5U-698 — glued-cell patterns. When the structure layer concatenates
# multiple table cells into a single heading, the result almost always shows
# one of these glue signatures:
#   "Wounded card:BP deck"  — colon directly followed by an uppercase letter,
#                             no whitespace. Distinguishes from "Chapter 1: Setup".
#   "deckAI"                — lowercase ASCII letter immediately followed by
#                             two or more uppercase ASCII letters. Distinguishes
#                             from legitimate CamelCase ("iPhone", "McDonald").
# These run *in addition* to the existing alpha-count check; any match means
# the text is refused as a page-title candidate (must-refuse bullet).
_COLON_GLUE_RE = re.compile(r":[A-Z]")
_CASE_GLUE_RE = re.compile(r"[a-z][A-Z]{2,}")


def is_garbage_title(text: str) -> bool:
    """Return True if *text* is unsuitable as a page title.

    Catches empty strings, lone list markers, standalone digits,
    strings with fewer than 2 alphabetic characters, and strings
    that carry glued-cell signatures from collapsed table headers
    (S5U-698 — "Wounded card:BP deckAI deck" class of failures).
    """
    stripped = text.strip()
    if not stripped:
        return True
    if _LONE_MARKER_RE.match(stripped):
        return True
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count < 2:
        return True
    if _COLON_GLUE_RE.search(stripped):
        return True
    return bool(_CASE_GLUE_RE.search(stripped))


def build_render_page(
    page_ir: PageIRV1,
    *,
    image_base_path: str = "",
    image_sources: dict[str, str] | None = None,
    concept_registry: ConceptRegistryV1 | None = None,
) -> RenderPageV1:
    """Map a translated PageIRV1 to a RenderPageV1 payload.

    Args:
        page_ir: The page IR to convert.
        image_base_path: URL prefix for figure image ``src`` values.
            When empty, asset_id is used as-is.
        image_sources: Per-asset src overrides (asset_id → src URL).
            Takes precedence over *image_base_path*.
        concept_registry: When provided, text content is scanned for
            concept patterns and surface forms in addition to icon detection.
    """
    render_blocks: list[RenderBlock] = []
    block_refs: list[str] = []
    figures: dict[str, RenderFigure] = {}
    title = ""

    caption_for_figure, consumed_caption_ids = _resolve_caption_attachments(page_ir)

    for block in page_ir.blocks:
        block_refs.append(block.block_id)
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        if isinstance(block, CaptionBlock):
            _dispatch_caption_block(block, render_blocks, consumed_caption_ids)
            continue

        # FigureBlock does not have translatable text children — handle separately
        if isinstance(block, FigureBlock):
            _emit_figure_block(
                block,
                render_blocks,
                figures,
                image_base_path=image_base_path,
                image_sources=image_sources,
                caption_for_figure=caption_for_figure,
            )
            continue

        if isinstance(block, TableBlock):
            render_blocks.append(
                RenderTableBlock(
                    id=block.block_id,
                    children=_convert_table_children(list(block.children)),
                )
            )
            continue

        if isinstance(block, CalloutBlock):
            # S5U-581: callout blocks now produce RenderCalloutBlock instead
            # of being silently dropped. The IR ``variant`` is propagated
            # verbatim so the web component can stylize via ``data-variant``.
            render_blocks.append(
                RenderCalloutBlock(
                    id=block.block_id,
                    variant=block.variant,
                    children=_convert_inline_nodes(list(block.children)),
                )
            )
            continue

        children = _convert_inline_nodes(list(block.children))

        if block.type == "heading":
            if not title:
                candidate = " ".join(c.text for c in children if isinstance(c, RenderTextInline))
                if not is_garbage_title(candidate):
                    title = candidate
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
        glossary_mentions=_extract_concept_mentions(page_ir, concept_registry),
        source_map=RenderSourceMap(
            document_id=page_ir.document_id,
            page_id=page_ir.page_id,
            block_refs=block_refs,
        ),
    )


def _emit_figure_block(
    block: FigureBlock,
    render_blocks: list[RenderBlock],
    figures: dict[str, RenderFigure],
    *,
    image_base_path: str,
    image_sources: dict[str, str] | None,
    caption_for_figure: dict[str, str],
) -> None:
    """Append a RenderFigureBlock and register its RenderFigure entry."""
    asset_id = block.asset_id
    render_blocks.append(
        RenderFigureBlock(
            id=block.block_id,
            asset_id=asset_id,
            children=_convert_inline_nodes(list(block.children)),
        )
    )
    if image_sources and asset_id in image_sources:
        src = image_sources[asset_id]
    elif image_base_path:
        src = f"{image_base_path}/{asset_id}"
    else:
        src = asset_id
    figures[asset_id] = RenderFigure(
        src=src,
        alt=asset_id,
        caption=caption_for_figure.get(asset_id, ""),
    )


def _dispatch_caption_block(
    block: CaptionBlock,
    render_blocks: list[RenderBlock],
    consumed_caption_ids: set[str],
) -> None:
    """S5U-737: dispatch a top-level CaptionBlock.

    Attached captions (``block.block_id in consumed_caption_ids``) are
    already folded into ``RenderFigure.caption`` by ``_emit_figure_block``
    via the ``caption_for_figure`` map, so they are dropped from the
    top-level block stream here. Orphan captions (block_id not in the
    consumed set) are emitted as a ``RenderCaptionBlock`` instead — pre-
    S5U-737 they were silently dropped, leaking translatable prose.
    """
    if block.block_id in consumed_caption_ids:
        return
    render_blocks.append(
        RenderCaptionBlock(
            id=block.block_id,
            children=_convert_inline_nodes(list(block.children)),
        )
    )


def _resolve_caption_attachments(page_ir: PageIRV1) -> tuple[dict[str, str], set[str]]:
    """S5U-700: fold each attached CaptionBlock into its owning figure.

    Returns a tuple of ``(caption_for_figure, consumed_caption_ids)``:

    * ``caption_for_figure`` — mapping of figure asset_id → caption text,
      consumed by ``_emit_figure_block`` to populate
      ``RenderFigure.caption``.
    * ``consumed_caption_ids`` — the ``block_id`` set of every
      ``CaptionBlock`` that was successfully attached to a figure on the
      page. The caller uses this set to distinguish attached captions
      (drop from the top-level block stream — already folded into
      RenderFigure.caption) from orphan captions (S5U-737 — emit as a
      ``RenderCaptionBlock`` so translatable prose survives).
    """
    caption_for_figure: dict[str, str] = {}
    consumed_caption_ids: set[str] = set()
    figure_id_to_asset: dict[str, str] = {
        b.block_id: b.asset_id for b in page_ir.blocks if isinstance(b, FigureBlock)
    }
    for block in page_ir.blocks:
        if not (isinstance(block, CaptionBlock) and block.figure_block_id):
            continue
        target_asset = figure_id_to_asset.get(block.figure_block_id)
        if target_asset is None:
            continue
        consumed_caption_ids.add(block.block_id)
        text = " ".join(
            c.text for c in block.children if isinstance(c, TextInline) and c.text.strip()
        ).strip()
        if text:
            caption_for_figure[target_asset] = text
    return caption_for_figure, consumed_caption_ids


def _convert_inline_nodes(nodes: list[InlineNode]) -> list[RenderInlineNode]:
    """Convert IR inline nodes to render inline nodes.

    S5U-739 — ``figure_ref`` round-trips. S5U-745 — ``term_mark`` /
    ``xref`` flatten to ``RenderTextInline`` (were: silently dropped);
    ``GlossaryText`` re-highlights surface forms from the registry, so
    per-instance term_mark link metadata is redundant. The trailing
    ``assert_never`` makes the dispatch exhaustive — a future 7th
    ``InlineNode`` variant with no render branch fails mypy --strict.
    """
    result: list[RenderInlineNode] = []
    for node in nodes:
        if isinstance(node, TextInline):
            result.append(RenderTextInline(text=node.text, marks=list(node.marks)))
        elif isinstance(node, IconInline):
            sym_id = node.symbol_id
            alt = sym_id.removeprefix("sym.").capitalize()
            result.append(RenderIconInline(symbol_id=sym_id, alt=alt))
        elif isinstance(node, FigureRefInline):
            result.append(RenderFigureRefInline(asset_id=node.asset_id, label=node.label))
        elif isinstance(node, LineBreakInline):
            result.append(RenderTextInline(text="\n"))
        elif isinstance(node, TermMarkInline):
            result.append(RenderTextInline(text=node.surface_form))
        elif isinstance(node, XrefInline):
            result.append(RenderTextInline(text=node.label))
        else:
            assert_never(node)
    return result


def _convert_table_cell(cell: TableCellBlock) -> RenderTableCellBlock:
    """S5U-704 — translate an IR TableCellBlock to its render counterpart."""
    return RenderTableCellBlock(
        id=cell.block_id,
        header=cell.header,
        children=_convert_inline_nodes(list(cell.children)),
    )


def _convert_table_row(row: TableRowBlock) -> RenderTableRowBlock:
    """S5U-704 — translate an IR TableRowBlock to its render counterpart."""
    return RenderTableRowBlock(
        id=row.block_id,
        header=row.header,
        cells=[_convert_table_cell(c) for c in row.cells],
    )


def _convert_table_children(children: list[TableChild]) -> list[RenderTableChild]:
    """Translate a ``TableBlock.children`` sequence to render-side children.

    S5U-704 — children may be either structured rows (``TableRowBlock``)
    or legacy flat inlines.  Rows are translated cell-by-cell; legacy
    inlines fall through to ``_convert_inline_nodes``.
    """
    result: list[RenderTableChild] = []
    flat_inlines: list[InlineNode] = []

    def flush_inlines() -> None:
        if not flat_inlines:
            return
        result.extend(_convert_inline_nodes(list(flat_inlines)))
        flat_inlines.clear()

    for child in children:
        if isinstance(child, TableRowBlock):
            flush_inlines()
            result.append(_convert_table_row(child))
        else:
            flat_inlines.append(child)
    flush_inlines()
    return result


def _extract_concept_mentions(
    page_ir: PageIRV1,
    concept_registry: ConceptRegistryV1 | None = None,
) -> list[str]:
    """Extract concept mentions from icon annotations and text content."""
    mentions: list[str] = []
    seen: set[str] = set()
    text_patterns = build_text_pattern_index(concept_registry) if concept_registry else []

    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue

        # S5U-704 — flatten TableRowBlock/TableCellBlock descendants so
        # concept detection still sees every inline.  Non-table blocks
        # return their own children unchanged.
        inlines: list[InlineNode]
        if isinstance(block, TableBlock):
            inlines = iter_table_inlines(block)
        else:
            inlines = list(block.children)

        # Icon-based detection
        for child in inlines:
            if isinstance(child, IconInline):
                concept = f"concept.{child.symbol_id.removeprefix('sym.')}"
                if concept not in seen:
                    seen.add(concept)
                    mentions.append(concept)

        # Text-based detection: concatenate all TextInline texts in the
        # block so phrases spanning node boundaries are found.
        if text_patterns:
            full_text = "".join(
                child.text if isinstance(child, TextInline) else " " for child in inlines
            )
            if full_text:
                match_text_patterns(full_text, text_patterns, seen, mentions)

    return mentions

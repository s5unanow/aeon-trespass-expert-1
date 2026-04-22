"""Build RenderPageV1 from translated PageIRV1."""

from __future__ import annotations

import re

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.page_ir_v1 import (
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    InlineNode,
    LineBreakInline,
    PageIRV1,
    TextInline,
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
    RenderTableBlock,
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

    caption_for_figure = _resolve_caption_attachments(page_ir)

    for block in page_ir.blocks:
        block_refs.append(block.block_id)
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue
        if isinstance(block, CaptionBlock):
            # S5U-700 Must-refuse M2: captions without a resolvable owning
            # figure are refused instead of rendered as detached prose.
            # Attached captions (block_id in consumed_caption_ids) are
            # folded into RenderFigure.caption by _emit_figure_block, so
            # they are also dropped from the top-level block stream.
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
        elif block.type == "table":
            render_blocks.append(RenderTableBlock(id=block.block_id, children=children))
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


def _resolve_caption_attachments(page_ir: PageIRV1) -> dict[str, str]:
    """S5U-700: fold each attached CaptionBlock into its owning figure.

    Returns a mapping of figure asset_id → caption text, consumed by
    ``_emit_figure_block`` to populate ``RenderFigure.caption``. Orphan
    CaptionBlocks (no ``figure_block_id`` or pointer does not resolve to
    a FigureBlock on the page) are skipped; the caller drops every
    CaptionBlock from the render output per Must-refuse M2.
    """
    caption_for_figure: dict[str, str] = {}
    figure_id_to_asset: dict[str, str] = {
        b.block_id: b.asset_id for b in page_ir.blocks if isinstance(b, FigureBlock)
    }
    for block in page_ir.blocks:
        if not (isinstance(block, CaptionBlock) and block.figure_block_id):
            continue
        target_asset = figure_id_to_asset.get(block.figure_block_id)
        if target_asset is None:
            continue
        text = " ".join(
            c.text for c in block.children if isinstance(c, TextInline) and c.text.strip()
        ).strip()
        if text:
            caption_for_figure[target_asset] = text
    return caption_for_figure


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
        elif node.type == "line_break":
            assert isinstance(node, LineBreakInline)
            result.append(RenderTextInline(text="\n"))
    return result


def _extract_concept_mentions(
    page_ir: PageIRV1,
    concept_registry: ConceptRegistryV1 | None = None,
) -> list[str]:
    """Extract concept mentions from icon annotations and text content."""
    mentions: list[str] = []
    seen: set[str] = set()
    text_patterns = _build_text_pattern_index(concept_registry) if concept_registry else []

    for block in page_ir.blocks:
        if isinstance(block, (DividerBlock, UnknownBlock)):
            continue

        # Icon-based detection
        for child in block.children:
            if isinstance(child, IconInline):
                concept = f"concept.{child.symbol_id.removeprefix('sym.')}"
                if concept not in seen:
                    seen.add(concept)
                    mentions.append(concept)

        # Text-based detection: concatenate all TextInline texts in the
        # block so phrases spanning node boundaries are found.
        if text_patterns:
            full_text = "".join(
                child.text if isinstance(child, TextInline) else " " for child in block.children
            )
            if full_text:
                _match_text_patterns(full_text, text_patterns, seen, mentions)

    return mentions


def _match_text_patterns(
    text: str,
    patterns: list[tuple[re.Pattern[str], str, int]],
    seen: set[str],
    mentions: list[str],
) -> None:
    """Match text patterns with longest-match-first span deduplication.

    Each pattern carries a specificity score (lower = more specific):
    0 = lemma match, 1 = pattern/surface-form match.
    When spans overlap, the longest match wins; ties broken by specificity.
    """
    hits: list[tuple[int, int, str, int]] = []
    for pattern, concept_id, specificity in patterns:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), concept_id, specificity))

    # Sort: longest span first, then most specific, then earliest position
    hits.sort(key=lambda h: (-(h[1] - h[0]), h[3], h[0]))

    # Greedily accept longest matches; skip overlapping shorter ones
    claimed: list[tuple[int, int]] = []
    for start, end, concept_id, _spec in hits:
        if concept_id in seen:
            continue
        if any(start < ce and end > cs for cs, ce in claimed):
            continue
        claimed.append((start, end))
        seen.add(concept_id)
        mentions.append(concept_id)


def _build_text_pattern_index(
    registry: ConceptRegistryV1,
) -> list[tuple[re.Pattern[str], str, int]]:
    """Build compiled regex patterns for text-based concept detection.

    Returns (compiled_pattern, concept_id, specificity) tuples.
    Specificity 0 = lemma match, 1 = pattern/surface-form match.
    """
    index: list[tuple[re.Pattern[str], str, int]] = []
    for concept in registry.concepts:
        lemma_lower = concept.source.lemma.lower()
        for text in (*concept.source.patterns, *concept.target.allowed_surface_forms):
            if text:
                specificity = 0 if text.lower() == lemma_lower else 1
                pat = re.compile(r"\b" + re.escape(text) + r"\b", re.IGNORECASE)
                index.append((pat, concept.concept_id, specificity))
    return index

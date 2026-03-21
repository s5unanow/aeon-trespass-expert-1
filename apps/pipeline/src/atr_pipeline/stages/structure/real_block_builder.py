"""Real block builder — structure recovery for actual ATO rulebook pages.

All font names, size thresholds, and layout constants are supplied via
``StructureConfig`` (see ``atr_pipeline.config.models``).  Default values
match the ATO Core Rulebook v1.1 analysis.
"""

from __future__ import annotations

import re

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.services.assets.inline_placer import place_icons_in_inlines
from atr_pipeline.services.assets.resolver import ResolvedSymbolPlacement
from atr_pipeline.stages.structure.furniture import FurnitureMap
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import ImageBlockEvidence, NativePageV1, SpanEvidence
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    InlineNode,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1


def _classify_span(span: SpanEvidence, cfg: StructureConfig) -> str:
    """Classify a span into a structural role."""
    if span.bbox.y0 >= cfg.footer_y_threshold:
        return "footer"
    if span.font_name in cfg.heading_fonts and span.font_size >= cfg.heading_min_size:
        return "heading"
    if span.font_name in cfg.decorative_fonts:
        return "decorative"
    if span.font_name == cfg.bold_font and span.font_size >= cfg.subheading_bold_min_size:
        return "subheading"
    if span.font_name == cfg.dingbat_font:
        return "bullet"
    if span.font_name == cfg.italic_font:
        return "italic"
    if span.font_name == cfg.bold_font:
        return "bold"
    if span.font_name == cfg.bold_italic_font:
        return "bold_italic"
    return "body"


def _same_line(a: SpanEvidence, b: SpanEvidence, tolerance: float = 3.0) -> bool:
    """Check if two spans are on the same line (similar y position)."""
    return abs(a.bbox.y0 - b.bbox.y0) < tolerance


def _spans_to_text_inline(
    spans: list[SpanEvidence],
    cfg: StructureConfig,
) -> list[TextInline]:
    """Convert a group of spans into TextInline nodes, merging adjacent same-role spans."""
    if not spans:
        return []

    inlines: list[TextInline] = []
    for span in spans:
        role = _classify_span(span, cfg)
        marks: list[str] = []
        if role == "bold" or role == "subheading":
            marks = ["bold"]
        elif role == "italic":
            marks = ["italic"]
        elif role == "bold_italic":
            marks = ["bold", "italic"]

        text = span.text
        if not text.strip():
            continue

        # Ensure whitespace between adjacent spans
        if inlines:
            prev_text = inlines[-1].text
            if prev_text and text and not prev_text[-1].isspace() and not text[0].isspace():
                text = " " + text

        # Merge with previous if same marks
        if inlines and inlines[-1].marks == marks:
            inlines[-1] = TextInline(
                text=inlines[-1].text + text,
                marks=marks,
                lang=LanguageCode.EN,
            )
        else:
            inlines.append(TextInline(text=text, marks=marks, lang=LanguageCode.EN))

    return inlines


def _significant_image_blocks(
    native: NativePageV1,
    cfg: StructureConfig,
) -> list[ImageBlockEvidence]:
    """Return image blocks large enough to warrant a FigureBlock.

    Filters by bounding-box size in PDF points and excludes images that sit
    entirely within the footer region.
    """
    results: list[ImageBlockEvidence] = []
    for img in native.image_blocks:
        w = img.bbox.x1 - img.bbox.x0
        h = img.bbox.y1 - img.bbox.y0
        if w < cfg.figure_min_width_pt or h < cfg.figure_min_height_pt:
            continue
        if img.bbox.y0 >= cfg.footer_y_threshold:
            continue
        results.append(img)
    return results


def _image_overlaps_text(
    img: ImageBlockEvidence,
    spans: list[SpanEvidence],
    tolerance: float = 5.0,
) -> bool:
    """Check whether an image's bbox substantially overlaps with text spans."""
    for span in spans:
        # If the bounding boxes overlap vertically and horizontally
        if (
            img.bbox.x0 < span.bbox.x1 + tolerance
            and img.bbox.x1 > span.bbox.x0 - tolerance
            and img.bbox.y0 < span.bbox.y1 + tolerance
            and img.bbox.y1 > span.bbox.y0 - tolerance
        ):
            return True
    return False


# Sentence boundary: ". " followed by uppercase Latin or Cyrillic letter.
_SENTENCE_BOUNDARY_RE = re.compile(r"\. (?=[A-ZА-ЯЁ])")  # noqa: RUF001


def _split_long_paragraphs(
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

        # We need to split children list at a sentence boundary.
        # Strategy: walk through children accumulating text length; when we
        # exceed *max_chars* find the last sentence boundary in the
        # accumulated text and split there.
        remaining_children: list[InlineNode] = list(block.children)
        base_id = block.block_id
        part = 0

        while remaining_children:
            remaining_text = "".join(c.text for c in remaining_children if hasattr(c, "text"))
            if len(remaining_text) <= max_chars:
                part_id = f"{base_id}.{part}" if part > 0 else base_id
                result.append(ParagraphBlock(block_id=part_id, children=remaining_children))
                break

            # Build a mapping of character offset → (child_index, char_within_child)
            char_offset = 0
            offset_map: list[tuple[int, int]] = []  # (child_idx, pos_in_child)
            for ci, child in enumerate(remaining_children):
                if hasattr(child, "text"):
                    for pos in range(len(child.text)):
                        offset_map.append((ci, pos))
                    char_offset += len(child.text)

            # Find the last sentence boundary before max_chars
            accumulated = remaining_text[:max_chars]
            split_pos = -1
            for m in _SENTENCE_BOUNDARY_RE.finditer(accumulated):
                # Split after the period+space → keep ". " with the first part
                split_pos = m.start() + 2  # position right after ". "

            if split_pos <= 0:
                # No sentence boundary found before limit; keep block as-is
                part_id = f"{base_id}.{part}" if part > 0 else base_id
                result.append(ParagraphBlock(block_id=part_id, children=remaining_children))
                break

            # Map split_pos back to child index and position
            child_idx, pos_in_child = offset_map[split_pos - 1]
            # split_pos - 1 is the last char that goes into the first part

            # Build first-part children
            first_children: list[InlineNode] = []
            second_children: list[InlineNode] = []

            for ci, child in enumerate(remaining_children):
                if ci < child_idx:
                    first_children.append(child)
                elif ci == child_idx and isinstance(child, TextInline):
                    # Split this text child
                    cut = pos_in_child + 1
                    left_text = child.text[:cut]
                    right_text = child.text[cut:]
                    if left_text:
                        first_children.append(
                            TextInline(
                                text=left_text,
                                marks=child.marks,
                                lang=child.lang,
                            )
                        )
                    if right_text:
                        second_children.append(
                            TextInline(
                                text=right_text,
                                marks=child.marks,
                                lang=child.lang,
                            )
                        )
                elif ci == child_idx:
                    # Non-text child (icon) at the split boundary → put in second
                    second_children.append(child)
                else:
                    second_children.append(child)

            part_id = f"{base_id}.{part}" if part > 0 else base_id
            if first_children:
                result.append(ParagraphBlock(block_id=part_id, children=first_children))
            part += 1
            remaining_children = second_children

    return result


def _deduplicate_blocks(blocks: list[object]) -> list[object]:
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


def build_page_ir_real(
    native: NativePageV1,
    symbols: SymbolMatchSetV1 | None = None,
    *,
    config: StructureConfig | None = None,
    furniture: FurnitureMap | None = None,
    placements: list[ResolvedSymbolPlacement] | None = None,
) -> PageIRV1:
    """Build PageIRV1 from real page evidence using font-based heuristics."""
    cfg = config or StructureConfig()
    furniture_map = furniture or FurnitureMap()
    # Collect significant images (even if there are no text spans)
    figure_images = _significant_image_blocks(native, cfg)
    # Filter out images that overlap heavily with text
    non_footer_spans = [s for s in native.spans if s.bbox.y0 < cfg.footer_y_threshold]
    figure_images = [
        img for img in figure_images if not _image_overlaps_text(img, non_footer_spans)
    ]

    if not native.spans and not figure_images:
        return PageIRV1(
            document_id=native.document_id,
            page_id=native.page_id,
            page_number=native.page_number,
            language=LanguageCode.EN,
            dimensions_pt=native.dimensions_pt,
        )

    # Classify all spans
    classified: list[tuple[str, SpanEvidence]] = [(_classify_span(s, cfg), s) for s in native.spans]

    # Group spans into logical lines
    lines: list[list[tuple[str, SpanEvidence]]] = []
    current_line: list[tuple[str, SpanEvidence]] = []

    for role, span in classified:
        if role == "footer":
            continue  # Strip footer zone
        if furniture_map.is_furniture_span(span.span_id):
            continue  # Strip detected furniture

        if current_line and not _same_line(current_line[-1][1], span):
            lines.append(current_line)
            current_line = []
        current_line.append((role, span))

    if current_line:
        lines.append(current_line)

    # Build blocks from lines
    _Block = (
        HeadingBlock | ParagraphBlock | ListItemBlock | CalloutBlock | DividerBlock | FigureBlock
    )
    blocks: list[_Block] = []
    block_idx = 0
    current_para_spans: list[SpanEvidence] = []

    def flush_paragraph() -> None:
        nonlocal block_idx
        if not current_para_spans:
            return
        block_idx += 1
        block_id = f"{native.page_id}.b{block_idx:03d}"

        text_inlines = _spans_to_text_inline(current_para_spans, cfg)
        if not text_inlines:
            current_para_spans.clear()
            return

        # Insert icon nodes at matching positions
        inlines: list[TextInline | IconInline] = list(text_inlines)
        if placements is not None:
            inlines = place_icons_in_inlines(text_inlines, placements, current_para_spans)
        elif symbols:
            inlines = _insert_icons(text_inlines, current_para_spans, symbols, native.page_id)

        blocks.append(ParagraphBlock(block_id=block_id, children=inlines))  # type: ignore[arg-type]
        current_para_spans.clear()

    for line in lines:
        roles = {role for role, _ in line}
        spans_in_line = [s for _, s in line]

        # Heading line
        if roles & {"heading", "subheading"} and "body" not in roles:
            flush_paragraph()
            block_idx += 1
            block_id = f"{native.page_id}.b{block_idx:03d}"
            text = "".join(s.text for _, s in line if _classify_span(s, cfg) != "decorative")
            text = text.strip()
            if text:
                # Determine heading level
                max_size = max(s.font_size for _, s in line)
                level = 1 if max_size >= 14 else 2 if max_size >= 10 else 3
                blocks.append(
                    HeadingBlock(
                        block_id=block_id,
                        level=level,
                        children=[TextInline(text=text, lang=LanguageCode.EN)],
                    )
                )
            continue

        # Decorative-only line (skip, often visual noise)
        if roles == {"decorative"}:
            continue

        # Bullet/list line
        if "bullet" in roles:
            flush_paragraph()
            block_idx += 1
            block_id = f"{native.page_id}.b{block_idx:03d}"
            non_bullet = [s for r, s in line if r != "bullet"]
            inlines = _spans_to_text_inline(non_bullet, cfg)
            if inlines:
                blocks.append(ListItemBlock(block_id=block_id, children=inlines))  # type: ignore[arg-type]
            continue

        # Regular body/bold/italic spans → accumulate into paragraph.
        # Detect vertical gaps between consecutive lines to split paragraphs.
        if current_para_spans and spans_in_line:
            last_span = current_para_spans[-1]
            first_new = spans_in_line[0]
            # Measure the gap from the bottom of the last accumulated line
            # to the top of the new line.
            y_gap = first_new.bbox.y0 - last_span.bbox.y1
            font_size = first_new.font_size or last_span.font_size
            threshold = (
                font_size * cfg.paragraph_gap_factor if font_size > 0 else cfg.paragraph_gap_abs
            )
            if y_gap > threshold:
                flush_paragraph()

        current_para_spans.extend(spans_in_line)

    flush_paragraph()

    # Append FigureBlocks for significant images that don't overlap text
    asset_ids: list[str] = []
    for img in figure_images:
        block_idx += 1
        block_id = f"{native.page_id}.b{block_idx:03d}"
        asset_id = img.image_id
        blocks.append(
            FigureBlock(
                block_id=block_id,
                asset_id=asset_id,
                bbox=Rect(
                    x0=img.bbox.x0,
                    y0=img.bbox.y0,
                    x1=img.bbox.x1,
                    y1=img.bbox.y1,
                ),
                translatable=False,
            )
        )
        asset_ids.append(asset_id)

    # Post-processing: split overly long paragraphs, then deduplicate.
    blocks = _split_long_paragraphs(blocks)  # type: ignore[arg-type,assignment]
    blocks = _deduplicate_blocks(blocks)  # type: ignore[arg-type,assignment]

    reading_order = [b.block_id for b in blocks]

    return PageIRV1(
        document_id=native.document_id,
        page_id=native.page_id,
        page_number=native.page_number,
        language=LanguageCode.EN,
        dimensions_pt=native.dimensions_pt,
        blocks=blocks,  # type: ignore[arg-type]
        assets=asset_ids,
        reading_order=reading_order,
    )


def _insert_icons(
    inlines: list[TextInline],
    spans: list[SpanEvidence],
    symbols: SymbolMatchSetV1,
    page_id: str,
) -> list[TextInline | IconInline]:
    """Insert icon nodes into the inline sequence at correct x-positions.

    Filters symbol matches to those overlapping the vertical span region,
    sorts them by horizontal position, then interleaves them among the text
    inlines using average character width to track cumulative x-offsets.
    """
    if not symbols.matches or not spans:
        return list(inlines)

    region_y_min = min(s.bbox.y0 for s in spans) - 5
    region_y_max = max(s.bbox.y1 for s in spans) + 5

    block_matches = [
        m
        for m in symbols.matches
        if m.inline and m.bbox.y0 >= region_y_min and m.bbox.y1 <= region_y_max
    ]
    if not block_matches:
        return list(inlines)

    block_matches.sort(key=lambda m: m.bbox.x0)

    char_width = _avg_char_width_spans(spans)
    cum_x = min(s.bbox.x0 for s in spans)

    result: list[TextInline | IconInline] = []
    midx = 0

    for ti in inlines:
        while midx < len(block_matches) and block_matches[midx].bbox.x0 <= cum_x:
            m = block_matches[midx]
            result.append(
                IconInline(
                    symbol_id=m.symbol_id,
                    instance_id=m.instance_id,
                    bbox=m.bbox,
                    source_asset_id=m.source_asset_id,
                )
            )
            midx += 1
        result.append(ti)
        cum_x += len(ti.text) * char_width

    for m in block_matches[midx:]:
        result.append(
            IconInline(
                symbol_id=m.symbol_id,
                instance_id=m.instance_id,
                bbox=m.bbox,
                source_asset_id=m.source_asset_id,
            )
        )

    return result


def _avg_char_width_spans(spans: list[SpanEvidence]) -> float:
    """Compute average character width across spans."""
    total_chars = 0
    total_width = 0.0
    for s in spans:
        n = len(s.text)
        if n > 0:
            total_chars += n
            total_width += s.bbox.width
    return total_width / total_chars if total_chars > 0 else 10.0

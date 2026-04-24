"""Real block builder — structure recovery for actual ATO rulebook pages.

All font names, size thresholds, and layout constants are supplied via
``StructureConfig`` (see ``atr_pipeline.config.models``).  Default values
match the ATO Core Rulebook v1.1 analysis.
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.services.assets.inline_placer import place_icons_in_inlines
from atr_pipeline.services.assets.resolver import ResolvedSymbolPlacement
from atr_pipeline.stages.structure.block_filter import figure_overlap_span_ids
from atr_pipeline.stages.structure.block_postprocess import (
    dedup_icon_instances,
    deduplicate_blocks,
    merge_list_continuations,
    split_long_paragraphs,
)
from atr_pipeline.stages.structure.figure_extraction import (
    _image_overlaps_text,
    _significant_image_blocks,
)
from atr_pipeline.stages.structure.furniture import FurnitureMap
from atr_pipeline.stages.structure.icon_insertion import (
    _insert_icons,
    _insert_icons_line_aware,
)
from atr_pipeline.stages.structure.span_classify import (
    _NUMBERED_STEP_RE,
    _bbox_from_spans,
    _classify_span,
    _same_line,
    _spans_to_text_inline,
)
from atr_pipeline.stages.structure.table_assembly import (
    _build_table_row,
    _line_in_table_region,
    _split_spans_by_x_gap,
)
from atr_pipeline.stages.structure.text_normalize import normalize_text
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    IconInline,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableRowBlock,
    TextInline,
)
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1

# Re-exported for backward-compatibility with
# ``tests/unit/stages/structure/test_insert_icons.py`` which imports
# these helpers directly from this module. Keeping the re-export lets
# the extraction in S5U-710 leave test imports untouched.
__all__ = [
    "_insert_icons",
    "_insert_icons_line_aware",
    "build_page_ir_real",
]


def build_page_ir_real(
    native: NativePageV1,
    symbols: SymbolMatchSetV1 | None = None,
    *,
    config: StructureConfig | None = None,
    furniture: FurnitureMap | None = None,
    placements: list[ResolvedSymbolPlacement] | None = None,
    table_regions: list[Rect] | None = None,
) -> PageIRV1:
    """Build PageIRV1 from real page evidence using font-based heuristics."""
    cfg = config or StructureConfig()
    furniture_map = furniture or FurnitureMap()
    # Collect significant images (even if there are no text spans)
    figure_images = _significant_image_blocks(native, cfg)
    # Identify short text spans sitting on top of figure images (diagram labels).
    figure_span_ids = figure_overlap_span_ids(native.spans, figure_images)
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
        if role == "diagram_label":
            continue  # Strip diagram/figure label text
        if furniture_map.is_furniture_span(span.span_id):
            continue  # Strip detected furniture
        if span.span_id in figure_span_ids:
            continue  # Strip text overlapping figure images

        if current_line and not _same_line(current_line[-1][1], span):
            lines.append(current_line)
            current_line = []
        current_line.append((role, span))

    if current_line:
        lines.append(current_line)

    # Pre-scan heading lines to build a relative heading-level map.
    # Anchors the largest heading to its absolute-threshold level, then
    # increments for each smaller distinct size — so pages with multiple
    # heading depths get distinct levels instead of collapsing into one.
    _heading_sizes: set[float] = set()
    for _pre_ln in lines:
        _pre_roles = {r for r, _ in _pre_ln}
        if _pre_roles & {"heading", "subheading"} and "body" not in _pre_roles:
            _pre_txt = "".join(s.text for _, s in _pre_ln if _classify_span(s, cfg) != "decorative")
            _pre_txt = normalize_text(_pre_txt.strip())
            if _pre_txt and not _NUMBERED_STEP_RE.match(_pre_txt):
                _heading_sizes.add(max(s.font_size for _, s in _pre_ln))
    _sorted_hs = sorted(_heading_sizes, reverse=True)
    _size_to_level: dict[float, int] = {}
    if _sorted_hs:
        _base_lvl = 1 if _sorted_hs[0] >= 14 else 2 if _sorted_hs[0] >= 10 else 3
        _size_to_level = {sz: min(_base_lvl + i, 6) for i, sz in enumerate(_sorted_hs)}

    # Build blocks from lines
    _Block = (
        HeadingBlock
        | ParagraphBlock
        | ListItemBlock
        | CalloutBlock
        | DividerBlock
        | FigureBlock
        | TableBlock
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
            inlines = _insert_icons_line_aware(current_para_spans, symbols, native.page_id, cfg)

        para_bbox = _bbox_from_spans(current_para_spans)
        blocks.append(ParagraphBlock(block_id=block_id, bbox=para_bbox, children=inlines))  # type: ignore[arg-type]
        current_para_spans.clear()

    # Table accumulator — groups table-region lines into TableBlocks
    _tbl_regions = table_regions or []
    current_table_idx = -1
    current_table_rows: list[list[SpanEvidence]] = []

    def flush_table() -> None:
        nonlocal block_idx, current_table_idx
        if not current_table_rows:
            current_table_idx = -1
            return
        block_idx += 1
        block_id = f"{native.page_id}.b{block_idx:03d}"
        # S5U-704 — split each accumulated row's spans into cells by
        # horizontal x-gap and emit structured ``TableRowBlock`` children
        # in place of the legacy flat inline run.
        row_blocks: list[TableRowBlock] = []
        for ri, row_spans in enumerate(current_table_rows):
            cell_groups = _split_spans_by_x_gap(
                row_spans,
                cfg.table_body_cell_split_gap_pt,
            )
            row = _build_table_row(cell_groups, cfg, block_id, ri)
            if row is not None:
                row_blocks.append(row)
        all_spans = [s for row in current_table_rows for s in row]
        blocks.append(
            TableBlock(
                block_id=block_id,
                bbox=_bbox_from_spans(all_spans),
                children=list(row_blocks),
            )
        )
        current_table_rows.clear()
        current_table_idx = -1

    for line in lines:
        roles = {role for role, _ in line}
        spans_in_line = [s for _, s in line]

        # Check if this line belongs to a table region
        if _tbl_regions:
            tbl_idx = _line_in_table_region(spans_in_line, _tbl_regions)
            if tbl_idx >= 0:
                if current_table_idx >= 0 and current_table_idx != tbl_idx:
                    flush_table()
                elif current_table_idx < 0:
                    flush_paragraph()
                current_table_idx = tbl_idx
                current_table_rows.append(spans_in_line)
                continue
            flush_table()

        # Heading line
        if roles & {"heading", "subheading"} and "body" not in roles:
            flush_paragraph()
            # S5U-698: refuse to merge heading spans that sit across multiple
            # cells of a table-header row. When the line splits into ≥2 cell
            # groups at ``heading_cell_split_gap_pt``, emit the line as its
            # own standalone TableBlock (one TableRowBlock with one cell
            # per group, per S5U-704) *immediately* — not buffered into the
            # regular table accumulator. Emitting in place (rather than
            # buffering) keeps reading order intact when the split header is
            # followed by non-table content, and avoids synthetic-region-
            # index collisions when the next line belongs to a real table
            # region with a different ``tbl_idx`` (Codex round 1 findings).
            non_decorative = [s for _, s in line if _classify_span(s, cfg) != "decorative"]
            cell_groups = _split_spans_by_x_gap(
                non_decorative,
                cfg.heading_cell_split_gap_pt,
            )
            if len(cell_groups) >= 2:
                flush_table()  # close any open real-region table first
                block_idx += 1
                block_id = f"{native.page_id}.b{block_idx:03d}"
                header_row = _build_table_row(
                    cell_groups,
                    cfg,
                    block_id,
                    row_index=0,
                    header=True,
                )
                if header_row is not None:
                    blocks.append(
                        TableBlock(
                            block_id=block_id,
                            bbox=_bbox_from_spans(non_decorative),
                            children=[header_row],
                        )
                    )
                continue

            text = "".join(s.text for _, s in line if _classify_span(s, cfg) != "decorative")
            text = normalize_text(text.strip())
            if text:
                if _NUMBERED_STEP_RE.match(text):
                    # Standalone number → list item (merged with next para later)
                    block_idx += 1
                    block_id = f"{native.page_id}.b{block_idx:03d}"
                    blocks.append(
                        ListItemBlock(
                            block_id=block_id,
                            bbox=_bbox_from_spans(spans_in_line),
                            children=[TextInline(text=text, lang=LanguageCode.EN)],
                        )
                    )
                else:
                    block_idx += 1
                    block_id = f"{native.page_id}.b{block_idx:03d}"
                    max_size = max(s.font_size for _, s in line)
                    level = _size_to_level.get(max_size, 3)
                    blocks.append(
                        HeadingBlock(
                            block_id=block_id,
                            bbox=_bbox_from_spans(spans_in_line),
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
                item_bbox = _bbox_from_spans(non_bullet)
                blocks.append(ListItemBlock(block_id=block_id, bbox=item_bbox, children=inlines))  # type: ignore[arg-type]
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
            if abs(y_gap) > threshold:
                flush_paragraph()

        current_para_spans.extend(spans_in_line)

    flush_table()
    flush_paragraph()

    # Append FigureBlocks for significant images that don't overlap text
    asset_ids: list[str] = []
    for img in figure_images:
        block_idx += 1
        block_id = f"{native.page_id}.b{block_idx:03d}"
        asset_id = f"{native.page_id}.{img.image_id}"
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

    # Post-processing: merge list continuations, split long paragraphs, deduplicate.
    blocks = merge_list_continuations(blocks)  # type: ignore[arg-type,assignment]
    blocks = split_long_paragraphs(blocks)  # type: ignore[arg-type,assignment]
    blocks = deduplicate_blocks(blocks)  # type: ignore[arg-type,assignment]
    dedup_icon_instances(blocks)  # type: ignore[arg-type]

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

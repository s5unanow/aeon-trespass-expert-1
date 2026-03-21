"""Inline icon placer — insert resolved icons at correct positions in text.

Replaces the naive end-append logic in ``_insert_icons()`` with
position-aware insertion driven by ``ResolvedSymbolPlacement``.
"""

from __future__ import annotations

from atr_pipeline.services.assets.resolver import ResolvedSymbolPlacement
from atr_schemas.enums import SymbolAnchorKind
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import IconInline, TextInline


def place_icons_in_inlines(
    text_inlines: list[TextInline],
    placements: list[ResolvedSymbolPlacement],
    line_spans: list[SpanEvidence],
) -> list[TextInline | IconInline]:
    """Insert icons at correct positions among text inlines.

    Filters placements to INLINE and PREFIX for the given block's span range,
    then inserts ``IconInline`` nodes at the appropriate positions.

    - PREFIX: prepend at index 0
    - INLINE: walk text inlines accumulating x from span bboxes, insert at
      the position closest to ``insertion_x``
    """
    if not placements:
        return list(text_inlines)

    # Compute block y-range from spans to filter relevant placements
    if line_spans:
        block_y_min = min(s.bbox.y0 for s in line_spans) - 5
        block_y_max = max(s.bbox.y1 for s in line_spans) + 5
    else:
        return list(text_inlines)

    # Filter to INLINE and PREFIX placements within this block's y-range
    prefix_icons: list[IconInline] = []
    inline_placements: list[ResolvedSymbolPlacement] = []

    for p in placements:
        if p.match.bbox.y0 < block_y_min or p.match.bbox.y1 > block_y_max:
            continue
        if p.anchor_kind == SymbolAnchorKind.PREFIX:
            prefix_icons.append(_make_icon(p))
        elif p.anchor_kind == SymbolAnchorKind.INLINE:
            inline_placements.append(p)

    if not prefix_icons and not inline_placements:
        return list(text_inlines)

    # Sort inline placements by insertion_x
    inline_placements.sort(key=lambda p: p.insertion_x or 0.0)

    # Build x-position map from spans for text inlines
    span_x_positions = _build_span_x_map(line_spans)

    # Insert INLINE icons at correct positions
    result: list[TextInline | IconInline] = []
    placement_idx = 0
    cumulative_x = span_x_positions[0] if span_x_positions else 0.0

    for ti in text_inlines:
        # Insert any inline icons whose insertion_x comes before this text
        while placement_idx < len(inline_placements):
            p = inline_placements[placement_idx]
            ix = p.insertion_x or 0.0
            if ix <= cumulative_x:
                result.append(_make_icon(p))
                placement_idx += 1
            else:
                break

        result.append(ti)
        # Advance cumulative x based on text length proportional to span width
        text_len = len(ti.text)
        if span_x_positions and text_len > 0:
            cumulative_x += text_len * _avg_char_width(line_spans)

    # Append remaining inline icons
    while placement_idx < len(inline_placements):
        result.append(_make_icon(inline_placements[placement_idx]))
        placement_idx += 1

    # Prepend PREFIX icons
    for icon in reversed(prefix_icons):
        result.insert(0, icon)

    return result


def _make_icon(p: ResolvedSymbolPlacement) -> IconInline:
    return IconInline(
        symbol_id=p.match.symbol_id,
        instance_id=p.match.instance_id,
        bbox=p.match.bbox,
        source_asset_id=p.match.source_asset_id,
        anchor_kind=p.anchor_kind,
        confidence=p.confidence,
    )


def _build_span_x_map(spans: list[SpanEvidence]) -> list[float]:
    """Return sorted list of span start x-positions."""
    return sorted(s.bbox.x0 for s in spans)


def _avg_char_width(spans: list[SpanEvidence]) -> float:
    """Compute average character width across all spans."""
    total_chars = 0
    total_width = 0.0
    for s in spans:
        n = len(s.text)
        if n > 0:
            total_chars += n
            total_width += s.bbox.width
    if total_chars == 0:
        return 10.0  # fallback
    return total_width / total_chars

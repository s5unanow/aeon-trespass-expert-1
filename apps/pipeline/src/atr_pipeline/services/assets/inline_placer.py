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
    """
    if not placements or not line_spans:
        return list(text_inlines)

    prefix_icons, inline_placements = _filter_block_placements(placements, line_spans)

    if not prefix_icons and not inline_placements:
        return list(text_inlines)

    result = _interleave_inline_icons(text_inlines, inline_placements, line_spans)

    # Prepend PREFIX icons
    for icon in reversed(prefix_icons):
        result.insert(0, icon)

    return result


def _filter_block_placements(
    placements: list[ResolvedSymbolPlacement],
    line_spans: list[SpanEvidence],
) -> tuple[list[IconInline], list[ResolvedSymbolPlacement]]:
    """Filter and split placements into prefix icons and inline placements."""
    block_y_min = min(s.bbox.y0 for s in line_spans) - 5
    block_y_max = max(s.bbox.y1 for s in line_spans) + 5

    prefix_icons: list[IconInline] = []
    inline_placements: list[ResolvedSymbolPlacement] = []

    for p in placements:
        if p.match.bbox.y0 < block_y_min or p.match.bbox.y1 > block_y_max:
            continue
        if p.anchor_kind == SymbolAnchorKind.PREFIX:
            prefix_icons.append(_make_icon(p))
        elif p.anchor_kind == SymbolAnchorKind.INLINE:
            inline_placements.append(p)

    inline_placements.sort(key=lambda p: p.insertion_x or 0.0)
    return prefix_icons, inline_placements


def _interleave_inline_icons(
    text_inlines: list[TextInline],
    inline_placements: list[ResolvedSymbolPlacement],
    line_spans: list[SpanEvidence],
) -> list[TextInline | IconInline]:
    """Walk text inlines and insert INLINE icons at correct x-positions."""
    if not inline_placements:
        return list(text_inlines)

    span_starts = sorted(s.bbox.x0 for s in line_spans)
    char_width = _avg_char_width(line_spans)

    result: list[TextInline | IconInline] = []
    pidx = 0
    cum_x = span_starts[0] if span_starts else 0.0

    for ti in text_inlines:
        # Insert icons whose insertion_x comes before this text position
        while pidx < len(inline_placements):
            ix = inline_placements[pidx].insertion_x or 0.0
            if ix <= cum_x:
                result.append(_make_icon(inline_placements[pidx]))
                pidx += 1
            else:
                break
        result.append(ti)
        cum_x += len(ti.text) * char_width

    # Append remaining inline icons
    for p in inline_placements[pidx:]:
        result.append(_make_icon(p))

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

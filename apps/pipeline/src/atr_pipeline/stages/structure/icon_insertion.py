"""Position-aware icon insertion for real-page inline runs.

Extracted from ``real_block_builder`` in S5U-710. No behavior changes.

This is the legacy symbol-driven icon placement path — used when the
structure stage receives a ``SymbolMatchSetV1`` directly rather than
the resolver's ``ResolvedSymbolPlacement`` list. Two entry points:

* ``_insert_icons`` — single-line cumulative-x cursor,
* ``_insert_icons_line_aware`` — resets the cursor at every visual line
  so icons on a later line don't leak into the inline gaps of the
  earlier line.

Both are also imported directly by ``tests/unit/stages/structure/test_insert_icons.py``
via ``real_block_builder``'s re-export; do not change their names
without updating both the re-export and those tests.
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.span_classify import (
    _WORD_GAP_THRESHOLD,
    _group_spans_by_line,
    _spans_to_text_inline,
)
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import IconInline, TextInline
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1


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


def _insert_icons_line_aware(
    spans: list[SpanEvidence],
    symbols: SymbolMatchSetV1,
    page_id: str,
    cfg: StructureConfig,
) -> list[TextInline | IconInline]:
    """Insert icons with per-line x-tracking for multi-line paragraphs.

    Groups paragraph spans into visual lines and calls ``_insert_icons`` per
    line so the cumulative x-cursor resets at each line break.
    """
    result: list[TextInline | IconInline] = []
    prev_line_spans: list[SpanEvidence] = []
    for line_spans in _group_spans_by_line(spans):
        line_inlines = _spans_to_text_inline(line_spans, cfg)
        if not line_inlines:
            continue
        # Insert whitespace between lines unless spans are x-adjacent
        if result and isinstance(result[-1], TextInline) and prev_line_spans:
            prev_text = result[-1].text
            first_text = line_inlines[0].text
            if (
                prev_text
                and first_text
                and not prev_text[-1].isspace()
                and not first_text[0].isspace()
            ):
                gap = line_spans[0].bbox.x0 - prev_line_spans[-1].bbox.x1
                if abs(gap) > _WORD_GAP_THRESHOLD:
                    first = line_inlines[0]
                    line_inlines[0] = TextInline(
                        text=" " + first.text,
                        marks=first.marks,
                        lang=first.lang,
                    )
        result.extend(_insert_icons(line_inlines, line_spans, symbols, page_id))
        prev_line_spans = line_spans
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

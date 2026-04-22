"""Tests for multi-cell heading refusal in real_block_builder (S5U-698).

Regression coverage for p0054 (Wounded / Escalation Charts) where three
separate table-header cells on the same y-baseline were joined into a
single heading ``"Wounded card:BP deckAI deck"``.
"""

from __future__ import annotations

import re

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence


def _span(
    span_id: str,
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    font_name: str,
    font_size: float,
) -> SpanEvidence:
    x0, y0, x1, y1 = bbox
    return SpanEvidence(
        span_id=span_id,
        text=text,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        font_name=font_name,
        font_size=font_size,
        flags=0,
        color=0,
    )


def _native_page(spans: list[SpanEvidence]) -> NativePageV1:
    return NativePageV1(
        document_id="doc",
        page_id="p0054",
        page_number=54,
        dimensions_pt=PageDimensions(width=595.0, height=842.0),
        words=[],
        spans=spans,
        image_blocks=[],
    )


def test_multi_cell_heading_line_is_not_joined_into_one_heading() -> None:
    """p0054 regression — three heading-font spans with large x-gaps must
    NOT emit a single HeadingBlock with glued text ``"Wounded card:BP deckAI deck"``.

    The structure stage must refuse this merge: either split the cells into
    a table-header row, or at least preserve whitespace boundaries so the
    downstream render layer can recognise the multi-cell glue pattern.
    """
    cfg = StructureConfig()
    spans = [
        _span(
            "s1",
            "Wounded card:",
            (57.9, 75.8, 140.1, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
        _span(
            "s2",
            "BP deck",
            (167.3, 75.8, 208.0, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
        _span(
            "s3",
            "AI deck",
            (369.2, 75.8, 406.5, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
    ]
    native = _native_page(spans)
    ir = build_page_ir_real(native, config=cfg)

    headings = [b for b in ir.blocks if b.type == "heading"]
    for h in headings:
        text = "".join(c.text for c in h.children if hasattr(c, "text"))
        # The specific glued garbage seen in p0054 must never ship as a heading.
        assert text != "Wounded card:BP deckAI deck", (
            f"heading text must not be the cell-joined garbage form; got {text!r}"
        )
        # More generally: a heading with the glued cell-boundary pattern
        # (colon directly followed by an uppercase letter with no whitespace
        # between them) is refused — it is the marker that two table-header
        # cells were concatenated across a cell boundary.
        assert not re.search(r":[A-Z]", text), (
            f"heading text looks like glued table cells: {text!r}"
        )


def test_single_cell_heading_is_preserved() -> None:
    """Must-not-break bullet — a legitimate single-cell heading stays
    intact even with colon usage like ``"Chapter 1: Setup"``.
    """
    cfg = StructureConfig()
    spans = [
        _span(
            "s1",
            "Chapter 1: Setup",
            (57.9, 75.8, 240.0, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
    ]
    native = _native_page(spans)
    ir = build_page_ir_real(native, config=cfg)

    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 1
    text = "".join(c.text for c in headings[0].children if hasattr(c, "text"))
    assert "Chapter 1: Setup" in text


def test_heading_spans_with_small_gap_still_merge() -> None:
    """Adversarial — two heading-font spans separated only by a narrow
    word-gap (~5pt) should remain a single heading. The multi-cell split
    only fires on large horizontal gaps consistent with a multi-column
    table header, not ordinary word spacing within a headline.
    """
    cfg = StructureConfig()
    spans = [
        _span(
            "s1",
            "Wounded",
            (57.9, 75.8, 100.0, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
        _span(
            "s2",
            "Escalation",
            (105.0, 75.8, 170.0, 90.1),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
    ]
    native = _native_page(spans)
    ir = build_page_ir_real(native, config=cfg)

    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 1
    text = "".join(c.text for c in headings[0].children if hasattr(c, "text"))
    # Both words must be present; the small-gap case must not refuse-to-merge.
    assert "Wounded" in text
    assert "Escalation" in text

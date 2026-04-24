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
from atr_schemas.page_ir_v1 import iter_table_inlines


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


def test_multi_cell_heading_emits_standalone_table_block_before_later_blocks() -> None:
    """Codex round 1 regression — a multi-cell heading followed by a normal
    paragraph must emit the resulting TableBlock BEFORE the paragraph
    (reading order preserved). Prior to this guard the split rows were
    buffered in the table accumulator and only flushed at end-of-page, so
    later body blocks appeared ahead of the header in ``PageIR.blocks``.
    """
    cfg = StructureConfig()
    # Multi-cell heading on y=75
    heading_spans = [
        _span(
            "s1",
            "A",
            (60.0, 75.0, 80.0, 90.0),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
        _span(
            "s2",
            "B",
            (300.0, 75.0, 320.0, 90.0),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
    ]
    # Normal body paragraph on y=120 (far enough below to be a new block,
    # and in the Adonis-Regular body font so it does not trigger heading)
    body_spans = [
        _span(
            "s3",
            "Body paragraph text.",
            (60.0, 120.0, 240.0, 132.0),
            font_name="Adonis-Regular",
            font_size=9.0,
        ),
    ]
    native = _native_page(heading_spans + body_spans)
    ir = build_page_ir_real(native, config=cfg)

    block_types = [b.type for b in ir.blocks]
    # The split-header TableBlock must come before the body paragraph.
    assert block_types[0] == "table", (
        f"expected first block to be the split-header TableBlock; got {block_types}"
    )
    assert "paragraph" in block_types, f"body paragraph must still be emitted; got {block_types}"
    assert block_types.index("table") < block_types.index("paragraph"), (
        f"split-header TableBlock must precede the body paragraph in reading "
        f"order; got {block_types}"
    )


def test_multi_cell_heading_does_not_collide_with_real_table_region() -> None:
    """Codex round 1 regression — a multi-cell split heading emitted when
    ``table_regions`` are configured must NOT cause the subsequent real
    table-region body to be attached as a second, disjoint table. The split
    heading emits in place as its own TableBlock; the real-region body then
    opens a separate fresh table accumulator.
    """
    cfg = StructureConfig()
    # Split heading at y=75 (no table region contains this y)
    heading_spans = [
        _span(
            "h1",
            "A",
            (60.0, 75.0, 80.0, 90.0),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
        _span(
            "h2",
            "B",
            (300.0, 75.0, 320.0, 90.0),
            font_name="GreenleafLightPro",
            font_size=11.0,
        ),
    ]
    # Body span inside a declared table region (y=200..300, x=50..500)
    body_spans = [
        _span(
            "b1",
            "cell one",
            (60.0, 220.0, 120.0, 232.0),
            font_name="Adonis-Regular",
            font_size=9.0,
        ),
    ]
    table_region = Rect(x0=50.0, y0=200.0, x1=500.0, y1=300.0)
    native = _native_page(heading_spans + body_spans)

    ir = build_page_ir_real(native, config=cfg, table_regions=[table_region])

    tables = [b for b in ir.blocks if b.type == "table"]
    # Expect TWO tables: the split-header TableBlock, and the real-region
    # TableBlock. They are distinct blocks and must not share children.
    assert len(tables) == 2, (
        f"expected separate TableBlocks for split header and real region; "
        f"got {len(tables)} tables in {[b.type for b in ir.blocks]}"
    )
    first_texts = "".join(c.text for c in iter_table_inlines(tables[0]) if hasattr(c, "text"))
    second_texts = "".join(c.text for c in iter_table_inlines(tables[1]) if hasattr(c, "text"))
    # The split-header TableBlock must carry the header cell text.
    assert "A" in first_texts and "B" in first_texts, (
        f"split-header table lost its cell text: first_texts={first_texts!r}"
    )
    # The real-region TableBlock must carry the body cell text, not mixed
    # with the header.
    assert "cell one" in second_texts, (
        f"real-region table lost its body text: second_texts={second_texts!r}"
    )
    assert "cell one" not in first_texts, "header and body must not be merged into one table"


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

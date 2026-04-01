"""Regression tests for audited structure failure categories.

Each test reproduces a known failure mode from the full-book quality audit
using small synthetic fixtures, so the suite stays fast and deterministic.
"""

from __future__ import annotations

from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence

_DIMS = PageDimensions(width=612, height=792)
_SPAN_COUNTER = 0


def _span(
    text: str,
    *,
    font: str = "Adonis-Regular",
    size: float = 9.0,
    y0: float = 100.0,
    x0: float = 50.0,
    span_id: str = "",
) -> SpanEvidence:
    """Build a SpanEvidence with sensible defaults."""
    global _SPAN_COUNTER
    _SPAN_COUNTER += 1
    sid = span_id or f"s{_SPAN_COUNTER:04d}"
    return SpanEvidence(
        span_id=sid,
        text=text,
        font_name=font,
        font_size=size,
        bbox=Rect(x0=x0, y0=y0, x1=x0 + len(text) * 5.0, y1=y0 + size),
    )


def _page(spans: list[SpanEvidence]) -> NativePageV1:
    """Build a minimal NativePageV1 from spans."""
    return NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=_DIMS,
        words=[],
        spans=spans,
        image_blocks=[],
    )


# --- Long paragraph splitting ---


def _long_text() -> str:
    """Generate >600 chars of non-repetitive text with sentence boundaries."""
    sentences = [f"Sentence number {i} describes a unique rule about combat. " for i in range(20)]
    return "".join(sentences)


def test_long_paragraph_is_split_at_sentence_boundary() -> None:
    """A paragraph exceeding 600 chars should be split at a sentence boundary."""
    text = _long_text()
    assert len(text) > 600
    native = _page([_span(text, span_id="s0001")])

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) >= 2, "Long paragraph should be split"
    # Each resulting paragraph must end at or near a sentence boundary
    for p in paragraphs[:-1]:
        p_text = "".join(c.text for c in p.children if hasattr(c, "text"))
        assert p_text.rstrip().endswith("."), f"Split must be at sentence end: {p_text[-30:]!r}"


def test_paragraph_without_sentence_boundary_stays_unsplit() -> None:
    """A long paragraph with no sentence boundary is kept intact."""
    text = "a" * 700  # No periods at all
    native = _page([_span(text, span_id="s0001")])

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1, "No boundary → no split"


def test_split_paragraph_ids_are_sequential() -> None:
    """Split parts must get sequential block IDs with .N suffix."""
    text = _long_text()
    native = _page([_span(text, span_id="s0001")])

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) >= 2
    # First part keeps the base ID, subsequent parts get .1, .2, …
    assert paragraphs[0].block_id == "p0001.b001"
    assert paragraphs[1].block_id == "p0001.b001.1"


# --- Decorative icon leakage ---


def test_decorative_only_line_produces_no_block() -> None:
    """A line containing only decorative fonts must not emit a block."""
    native = _page(
        [
            _span("v", font="GreenleafBannersRegularL", size=12.0, span_id="s0001"),
        ]
    )

    ir = build_page_ir_real(native)
    assert len(ir.blocks) == 0, "Decorative-only line must be skipped"


def test_decorative_filtered_from_heading_text() -> None:
    """Decorative spans mixed into a heading line must not leak into heading text."""
    native = _page(
        [
            _span("v", font="GreenleafBannersRegularL", size=12.0, y0=100, x0=50, span_id="s0001"),
            _span(
                "Battle Phase",
                font="GreenleafLightPro",
                size=14.0,
                y0=100,
                x0=70,
                span_id="s0002",
            ),
        ]
    )

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 1
    heading_text = "".join(c.text for c in headings[0].children if hasattr(c, "text"))
    assert "v" not in heading_text, "Decorative glyph must not appear in heading"
    assert "Battle Phase" in heading_text


def test_decorative_in_body_line_does_not_crash() -> None:
    """Body spans mixed with decorative should produce a paragraph without crash."""
    native = _page(
        [
            _span("v", font="GreenleafBannersRegularL", size=9.0, y0=100, x0=50, span_id="s0001"),
            _span(
                "Some body text", font="Adonis-Regular", size=9.0, y0=100, x0=70, span_id="s0002"
            ),
        ]
    )

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) >= 1


# --- Duplicate text blocks ---


def test_consecutive_duplicate_blocks_are_deduplicated() -> None:
    """Two consecutive paragraphs with identical text should be deduplicated."""
    spans = [
        _span("Duplicate paragraph text here.", y0=100, span_id="s0001"),
        _span("Duplicate paragraph text here.", y0=200, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1, "Consecutive duplicates must collapse to one"


def test_non_consecutive_duplicates_are_kept() -> None:
    """Duplicates separated by a different block should both survive."""
    spans = [
        _span("Repeated text.", y0=100, span_id="s0001"),
        _span("Different text in between.", y0=200, span_id="s0002"),
        _span("Repeated text.", y0=300, span_id="s0003"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 3, "Non-consecutive duplicates must be kept"


def test_dedup_uses_first_80_chars() -> None:
    """Two blocks identical in the first 80 chars but different after should dedup.

    This is a deliberate trade-off: PDF double-extraction often produces
    near-identical blocks where only trailing punctuation or whitespace
    differs.  The lossy 80-char comparison handles these artifacts at the
    cost of discarding genuinely different blocks that share a long prefix.
    """
    prefix = "A" * 80
    spans = [
        _span(prefix + " first ending.", y0=100, span_id="s0001"),
        _span(prefix + " different ending.", y0=200, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1, "First-80-char match should dedup"


# --- Glued text / missing whitespace ---


def test_adjacent_spans_get_whitespace_inserted() -> None:
    """Two body spans without trailing/leading space should be separated."""
    spans = [
        _span("word1", y0=100, x0=50, span_id="s0001"),
        _span("word2", y0=100, x0=90, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1
    full_text = "".join(c.text for c in paragraphs[0].children if hasattr(c, "text"))
    assert "word1 word2" in full_text, f"Expected space between spans, got: {full_text!r}"


def test_spans_with_existing_whitespace_not_doubled() -> None:
    """Spans that already have a trailing/leading space should not get double spaces."""
    spans = [
        _span("hello ", y0=100, x0=50, span_id="s0001"),
        _span("world", y0=100, x0=90, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1
    full_text = "".join(c.text for c in paragraphs[0].children if hasattr(c, "text"))
    assert "  " not in full_text, f"Double space found: {full_text!r}"


def test_bold_to_regular_transition_preserves_whitespace() -> None:
    """Switching from bold to regular should still insert a space if needed."""
    spans = [
        _span("Bold", font="Adonis-Bold", size=9.0, y0=100, x0=50, span_id="s0001"),
        _span("Regular", font="Adonis-Regular", size=9.0, y0=100, x0=90, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1
    texts = [c.text for c in paragraphs[0].children if hasattr(c, "text")]
    full = "".join(texts)
    assert "Bold" in full and "Regular" in full
    # The two words should be separated by whitespace
    assert "Bold Regular" in full or "Bold " in texts[0], f"Missing space: {full!r}"


# --- Sparse / empty pages ---


def test_page_with_only_footer_spans_produces_no_blocks() -> None:
    """A page where all spans are in the footer region should produce empty IR."""
    spans = [
        _span("42", y0=800, span_id="s0001"),
        _span("Battle Phase", y0=805, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    assert len(ir.blocks) == 0, "Footer-only page must produce no blocks"


def test_page_with_single_whitespace_span_produces_no_blocks() -> None:
    """A page with only whitespace spans should produce empty IR."""
    spans = [
        _span("   ", y0=100, span_id="s0001"),
        _span("  \n  ", y0=200, span_id="s0002"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    assert len(ir.blocks) == 0, "Whitespace-only page must produce no blocks"


# --- Vertical gap paragraph splitting ---


def test_large_vertical_gap_splits_paragraphs() -> None:
    """Lines separated by more than font_size * gap_factor are separate paragraphs."""
    spans = [
        _span("First paragraph.", y0=100, span_id="s0001"),
        _span("Second paragraph.", y0=200, span_id="s0002"),  # 100pt gap >> 9*1.5
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 2, "Large vertical gap should split paragraphs"


def test_small_vertical_gap_keeps_single_paragraph() -> None:
    """Lines close together should merge into a single paragraph."""
    spans = [
        _span("Line one of paragraph.", y0=100, span_id="s0001"),
        _span("Line two of same paragraph.", y0=110, span_id="s0002"),  # 10pt ~ font_size
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(paragraphs) == 1, "Close lines should be one paragraph"


# --- Numbered step detection ---


def test_standalone_number_heading_becomes_list_item() -> None:
    """A heading line containing only a number (e.g., '1') should become a list item."""
    spans = [
        _span("1", font="Adonis-Bold", size=10.0, y0=100, x0=50, span_id="s0001"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    list_items = [b for b in ir.blocks if b.type == "list_item"]
    assert len(headings) == 0, "Standalone '1' must not become a heading"
    assert len(list_items) == 1, "Standalone '1' must become a list item"
    text = "".join(c.text for c in list_items[0].children if hasattr(c, "text"))
    assert text.strip() == "1"


def test_numbered_step_merged_with_following_paragraph() -> None:
    """A numbered heading ('1') followed by body text should merge into one list item."""
    spans = [
        _span("1", font="Adonis-Bold", size=10.0, y0=100, x0=50, span_id="s0001"),
        _span(
            "Place the tiles on the board.",
            font="Adonis-Regular",
            size=9.0,
            y0=112,
            x0=50,
            span_id="s0002",
        ),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    list_items = [b for b in ir.blocks if b.type == "list_item"]
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(headings) == 0, "Number must not become heading"
    assert len(list_items) == 1, "Should merge into one list item"
    assert len(paragraphs) == 0, "Continuation should be absorbed"
    text = "".join(c.text for c in list_items[0].children if hasattr(c, "text"))
    assert "1" in text
    assert "Place the tiles" in text


def test_real_heading_text_stays_heading() -> None:
    """A heading with actual text (not just a number) remains a heading."""
    spans = [
        _span("Battle Phase", font="Adonis-Bold", size=10.0, y0=100, x0=50, span_id="s0001"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 1, "Real heading text must stay a heading"


# --- List-item continuation merging ---


def test_bullet_item_continuation_merged() -> None:
    """A paragraph following a bullet list item at similar indentation should merge."""
    spans = [
        _span("l", font="ITCZapfDingbatsMedium", size=9.0, y0=100, x0=50, span_id="s0001"),
        _span("First item text", font="Adonis-Regular", size=9.0, y0=100, x0=65, span_id="s0002"),
        _span(
            "continuation of first item.",
            font="Adonis-Regular",
            size=9.0,
            y0=112,
            x0=65,
            span_id="s0003",
        ),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    list_items = [b for b in ir.blocks if b.type == "list_item"]
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(list_items) == 1, "Should have one merged list item"
    assert len(paragraphs) == 0, "Continuation should not be a separate paragraph"
    text = "".join(c.text for c in list_items[0].children if hasattr(c, "text"))
    assert "First item text" in text
    assert "continuation" in text


def test_paragraph_after_list_item_with_large_gap_stays_separate() -> None:
    """A paragraph far below a list item should NOT be merged."""
    spans = [
        _span("l", font="ITCZapfDingbatsMedium", size=9.0, y0=100, x0=50, span_id="s0001"),
        _span("Item text", font="Adonis-Regular", size=9.0, y0=100, x0=65, span_id="s0002"),
        _span(
            "Separate paragraph.",
            font="Adonis-Regular",
            size=9.0,
            y0=200,
            x0=50,
            span_id="s0003",
        ),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    list_items = [b for b in ir.blocks if b.type == "list_item"]
    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    assert len(list_items) == 1
    assert len(paragraphs) == 1, "Far paragraph must stay separate"


# --- Heading level hierarchy (S5U-441) ---


def test_multi_size_headings_get_distinct_levels() -> None:
    """Headings at different font sizes must produce distinct heading levels."""
    spans = [
        _span("Chapter Title", font="GreenleafLightPro", size=18.0, y0=80, span_id="s0001"),
        _span("Body text.", font="Adonis-Regular", size=9.0, y0=120, span_id="s0002"),
        _span("Section Heading", font="GreenleafLightPro", size=14.0, y0=200, span_id="s0003"),
        _span("More body.", font="Adonis-Regular", size=9.0, y0=240, span_id="s0004"),
        _span("Subsection", font="Adonis-Bold", size=10.0, y0=320, span_id="s0005"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 3, f"Expected 3 headings, got {len(headings)}"
    levels = [h.level for h in headings]
    assert levels[0] < levels[1] < levels[2], f"Levels must be strictly increasing: {levels}"


def test_single_size_headings_stay_same_level() -> None:
    """Headings all at the same font size must share one heading level."""
    spans = [
        _span("Heading A", font="Adonis-Bold", size=10.0, y0=100, span_id="s0001"),
        _span("Body text.", font="Adonis-Regular", size=9.0, y0=130, span_id="s0002"),
        _span("Heading B", font="Adonis-Bold", size=10.0, y0=200, span_id="s0003"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 2
    assert headings[0].level == headings[1].level, "Same-size headings must share one level"


# --- Config-driven table regions (S5U-442) ---


def test_config_table_region_produces_table_block() -> None:
    """Spans inside a config-driven table region become a TableBlock (S5U-442).

    Regression: when PyMuPDF fails to detect gridless tables, config overrides
    supply the table region. The structure stage must group those spans into
    a TableBlock rather than separate paragraphs.
    """
    spans = [
        _span("BP I", y0=110, x0=60, span_id="s0001"),
        _span("Shuffle a card into the deck.", y0=130, x0=60, span_id="s0002"),
        _span("BP II", y0=200, x0=60, span_id="s0003"),
        _span("Remove a card from battle.", y0=220, x0=60, span_id="s0004"),
    ]
    native = _page(spans)
    table_regions = [Rect(x0=55, y0=105, x1=550, y1=250)]

    ir = build_page_ir_real(native, table_regions=table_regions)
    tables = [b for b in ir.blocks if b.type == "table"]
    assert len(tables) >= 1, "Config-driven table region must produce TableBlock"
    table_text = " ".join(c.text for c in tables[0].children if hasattr(c, "text"))
    assert "BP I" in table_text
    assert "BP II" in table_text


def test_table_block_survives_render_stage() -> None:
    """TableBlock in page_ir must produce RenderTableBlock in render_page (S5U-442).

    Regression: the render stage silently dropped TableBlocks because the
    block type dispatcher had no 'table' branch. This must not regress.
    """
    from atr_pipeline.stages.render.page_builder import build_render_page
    from atr_schemas.enums import LanguageCode
    from atr_schemas.page_ir_v1 import PageIRV1, TableBlock, TextInline

    ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(
                block_id="p0001.b001",
                children=[TextInline(text="Row 1 data", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    render = build_render_page(ir)
    assert len(render.blocks) == 1, "TableBlock must not be dropped by render stage"
    assert render.blocks[0].kind == "table"


# --- Bare-number heading filter (S5U-443) ---


def test_bare_numbers_in_heading_font_become_list_items() -> None:
    """Standalone numbers in heading font must become list items, not headings.

    Regression: p0017 emitted bare numbers (17, 18, 19, 4) as headings
    because they used GreenleafLightPro font. The _NUMBERED_STEP_RE filter
    must redirect these to ListItemBlock.
    """
    spans = [
        _span("Real Heading", font="GreenleafLightPro", size=14.0, y0=50, span_id="s0001"),
        _span("Body text.", font="Adonis-Regular", size=9.0, y0=80, span_id="s0002"),
        _span("17", font="GreenleafLightPro", size=12.5, y0=120, span_id="s0003"),
        _span("18", font="GreenleafLightPro", size=12.5, y0=150, span_id="s0004"),
        _span("4", font="GreenleafLightPro", size=13.8, y0=180, span_id="s0005"),
        _span("More body.", font="Adonis-Regular", size=9.0, y0=210, span_id="s0006"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    list_items = [b for b in ir.blocks if b.type == "list_item"]

    # Only "Real Heading" should be a heading
    assert len(headings) == 1, f"Expected 1 heading, got {len(headings)}: {headings}"
    h_text = " ".join(c.text for c in headings[0].children if hasattr(c, "text"))
    assert "Real Heading" in h_text

    # Bare numbers should be list items
    li_texts = [" ".join(c.text for c in li.children if hasattr(c, "text")) for li in list_items]
    assert any("17" in t for t in li_texts), f"'17' missing from list items: {li_texts}"
    assert any("18" in t for t in li_texts), f"'18' missing from list items: {li_texts}"
    assert any("4" in t for t in li_texts), f"'4' missing from list items: {li_texts}"


def test_numbered_section_heading_preserved() -> None:
    """Numbered headings with descriptive text must remain headings.

    '3. Moving the Adversary' is a legitimate heading — only bare numbers
    like '17' or '4.' should be filtered.
    """
    spans = [
        _span(
            "3. Moving the Adversary",
            font="GreenleafLightPro",
            size=12.0,
            y0=50,
            span_id="s0001",
        ),
        _span("Body text.", font="Adonis-Regular", size=9.0, y0=80, span_id="s0002"),
        _span("4.", font="GreenleafLightPro", size=12.0, y0=120, span_id="s0003"),
    ]
    native = _page(spans)

    ir = build_page_ir_real(native)
    headings = [b for b in ir.blocks if b.type == "heading"]
    list_items = [b for b in ir.blocks if b.type == "list_item"]

    # "3. Moving the Adversary" is a heading
    assert len(headings) == 1
    h_text = " ".join(c.text for c in headings[0].children if hasattr(c, "text"))
    assert "Moving the Adversary" in h_text

    # "4." is a bare number step → list item
    assert len(list_items) >= 1

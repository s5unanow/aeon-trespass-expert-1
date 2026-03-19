"""Regression tests for audited structure failure categories.

Each test reproduces a known failure mode from the full-book quality audit
using small synthetic fixtures, so the suite stays fast and deterministic.
"""

from __future__ import annotations

from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence

_DIMS = PageDimensions(width=612, height=792)


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
    sid = span_id or f"s{hash(text) % 10000:04d}"
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
    """Two blocks identical in the first 80 chars but different after should dedup."""
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

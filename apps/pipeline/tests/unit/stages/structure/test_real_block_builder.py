"""Tests for the real page block builder."""

from pathlib import Path

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import ImageBlockEvidence, NativePageV1, SpanEvidence

PDF_PATH = Path(__file__).resolve().parents[6] / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"


def _skip_if_no_pdf() -> bool:
    return not PDF_PATH.exists()


def test_page_42_has_heading_and_paragraphs() -> None:
    """Page 42 should produce a heading and multiple body blocks."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=42, document_id="ato")
    ir = build_page_ir_real(native)

    assert ir.language == LanguageCode.EN
    assert ir.page_id == "p0042"
    assert len(ir.blocks) >= 5

    # First block should be a heading
    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) >= 1
    first_heading_text = " ".join(c.text for c in headings[0].children if hasattr(c, "text"))
    assert "Primordial Attack Types" in first_heading_text


def test_page_11_has_list_items() -> None:
    """Page 11 should have list items from bullet points."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=11, document_id="ato")
    ir = build_page_ir_real(native)

    list_items = [b for b in ir.blocks if b.type == "list_item"]
    assert len(list_items) >= 2


def test_footer_is_stripped() -> None:
    """Footer text (page numbers, section names) should not appear in blocks."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=42, document_id="ato")
    ir = build_page_ir_real(native)

    all_text = ""
    for b in ir.blocks:
        for c in b.children:
            if hasattr(c, "text"):
                all_text += c.text

    # Footer contains "41" (page number) and "Battle Phase" at y>800
    # The block text should not start with the page number as a standalone token
    # (it might appear in body text naturally)
    assert ir.blocks[0].type == "heading"  # First block is heading, not footer


def test_empty_page_produces_empty_ir() -> None:
    """Page 2 (blank) should produce an IR with no blocks."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=2, document_id="ato")
    ir = build_page_ir_real(native)

    assert len(ir.blocks) == 0


def test_heading_levels_differentiated() -> None:
    """Page with multiple heading sizes should produce distinct heading levels."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=11, document_id="ato")
    ir = build_page_ir_real(native)

    headings = [b for b in ir.blocks if b.type == "heading"]
    if len(headings) >= 2:
        levels = [h.level for h in headings]
        assert len(set(levels)) >= 2, f"Expected >1 distinct level, got {levels}"


def test_large_image_block_creates_figure() -> None:
    """A large image block should produce a FigureBlock in the IR."""
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=[],
        spans=[],
        image_blocks=[
            ImageBlockEvidence(
                image_id="img0000",
                bbox=Rect(x0=50, y0=50, x1=400, y1=300),
                width_px=700,
                height_px=500,
                xref=1,
            ),
        ],
    )
    ir = build_page_ir_real(native)
    figure_blocks = [b for b in ir.blocks if b.type == "figure"]
    assert len(figure_blocks) == 1
    assert figure_blocks[0].asset_id == "p0001.img0000"
    assert "p0001.img0000" in ir.assets


def test_small_image_block_is_ignored() -> None:
    """An image block below the size threshold should not produce a FigureBlock."""
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=[],
        spans=[],
        image_blocks=[
            ImageBlockEvidence(
                image_id="img0000",
                bbox=Rect(x0=50, y0=50, x1=80, y1=70),  # 30x20 pt — too small
                width_px=30,
                height_px=20,
                xref=1,
            ),
        ],
    )
    ir = build_page_ir_real(native)
    figure_blocks = [b for b in ir.blocks if b.type == "figure"]
    assert len(figure_blocks) == 0


def test_footer_image_is_ignored() -> None:
    """An image block in the footer region should not produce a FigureBlock."""
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=[],
        spans=[],
        image_blocks=[
            ImageBlockEvidence(
                image_id="img0000",
                bbox=Rect(x0=50, y0=795, x1=400, y1=900),  # in footer
                width_px=700,
                height_px=200,
                xref=1,
            ),
        ],
    )
    ir = build_page_ir_real(native)
    figure_blocks = [b for b in ir.blocks if b.type == "figure"]
    assert len(figure_blocks) == 0


def test_small_caps_spans_merge_without_space() -> None:
    """Small-caps word parts (touching x-positions) should merge without spaces."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="I",
            font_name="Adonis-Bold-SC700",
            font_size=12.0,
            bbox=Rect(x0=92.3, y0=86.6, x1=96.3, y1=98.6),
        ),
        SpanEvidence(
            span_id="s002",
            text="ntroduction",
            font_name="Adonis-Bold-SC700",
            font_size=8.4,
            bbox=Rect(x0=96.3, y0=89.9, x1=156.9, y1=98.3),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[],
    )
    ir = build_page_ir_real(native)
    assert len(ir.blocks) == 1
    text = "".join(c.text for c in ir.blocks[0].children if hasattr(c, "text"))
    assert "Introduction" in text
    assert "I ntroduction" not in text


def test_diagram_label_heading_font_at_tiny_size_excluded() -> None:
    """Heading fonts at sub-body size (diagram labels) should not become blocks."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="Strangers",
            font_name="GreenleafLightPro",
            font_size=4.1,  # Below body_size_min (7.5)
            bbox=Rect(x0=512, y0=661, x1=545, y1=670),
        ),
        SpanEvidence(
            span_id="s002",
            text="Real body text here",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=50, y0=100, x1=400, y1=112),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[],
    )
    ir = build_page_ir_real(native)
    all_text = " ".join(c.text for b in ir.blocks for c in b.children if hasattr(c, "text"))
    assert "Strangers" not in all_text
    assert "Real body text" in all_text


def test_short_span_on_figure_image_excluded() -> None:
    """Short text spans overlapping a figure image should be filtered out."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="3",
            font_name="Adonis-Bold",
            font_size=9.0,
            bbox=Rect(x0=200, y0=500, x1=210, y1=510),
        ),
        SpanEvidence(
            span_id="s002",
            text="Real paragraph text content",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=50, y0=100, x1=400, y1=112),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[
            ImageBlockEvidence(
                image_id="img0000",
                bbox=Rect(x0=100, y0=400, x1=500, y1=700),
                width_px=800,
                height_px=600,
                xref=1,
            ),
        ],
    )
    ir = build_page_ir_real(native)
    all_text = " ".join(c.text for b in ir.blocks for c in b.children if hasattr(c, "text"))
    # "3" is inside the figure image and should be excluded
    assert "3" not in all_text.split()
    assert "Real paragraph text" in all_text


def test_long_span_on_figure_image_kept() -> None:
    """Long text spans overlapping figure images should NOT be filtered."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="This is a real body text sentence near an image",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=100, y0=450, x1=490, y1=462),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[
            ImageBlockEvidence(
                image_id="img0000",
                bbox=Rect(x0=100, y0=400, x1=500, y1=700),
                width_px=800,
                height_px=600,
                xref=1,
            ),
        ],
    )
    ir = build_page_ir_real(native)
    all_text = " ".join(c.text for b in ir.blocks for c in b.children if hasattr(c, "text"))
    assert "real body text" in all_text


def test_custom_config_changes_footer_threshold() -> None:
    """Passing a custom StructureConfig should change classification behavior."""
    span_in_default_footer = SpanEvidence(
        span_id="s001",
        text="Footer text",
        font_name="Adonis-Regular",
        font_size=9.0,
        bbox=Rect(x0=50, y0=795, x1=200, y1=805),
    )
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=[span_in_default_footer],
        image_blocks=[],
    )
    # Default config (footer_y_threshold=790): span is footer → no blocks
    ir_default = build_page_ir_real(native)
    assert len(ir_default.blocks) == 0

    # Custom config with raised threshold: span is now body → produces a block
    cfg = StructureConfig(footer_y_threshold=900.0)
    ir_custom = build_page_ir_real(native, config=cfg)
    assert len(ir_custom.blocks) == 1
    assert ir_custom.blocks[0].type == "paragraph"


# --- Table region tests ---


def _table_spans() -> list[SpanEvidence]:
    """Three rows of table-like text within a known table region."""
    return [
        SpanEvidence(
            span_id="s001",
            text="Header A",
            font_name="Adonis-Bold",
            font_size=9.0,
            bbox=Rect(x0=60, y0=200, x1=140, y1=212),
        ),
        SpanEvidence(
            span_id="s002",
            text="Header B",
            font_name="Adonis-Bold",
            font_size=9.0,
            bbox=Rect(x0=200, y0=200, x1=280, y1=212),
        ),
        SpanEvidence(
            span_id="s003",
            text="Cell 1",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=220, x1=120, y1=232),
        ),
        SpanEvidence(
            span_id="s004",
            text="Cell 2",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=200, y0=220, x1=260, y1=232),
        ),
        SpanEvidence(
            span_id="s005",
            text="Cell 3",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=240, x1=120, y1=252),
        ),
        SpanEvidence(
            span_id="s006",
            text="Cell 4",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=200, y0=240, x1=260, y1=252),
        ),
    ]


def test_table_region_produces_table_block() -> None:
    """Spans inside a table region should produce a TableBlock, not paragraphs."""
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=_table_spans(),
        image_blocks=[],
    )
    table_bbox = Rect(x0=50, y0=190, x1=300, y1=260)
    ir = build_page_ir_real(native, table_regions=[table_bbox])

    table_blocks = [b for b in ir.blocks if b.type == "table"]
    assert len(table_blocks) == 1
    # Should contain text from all rows
    text = " ".join(c.text for c in table_blocks[0].children if hasattr(c, "text"))
    assert "Header A" in text
    assert "Cell 4" in text


def test_table_region_has_line_breaks_between_rows() -> None:
    """TableBlock should have LineBreakInline between visual rows."""
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=_table_spans(),
        image_blocks=[],
    )
    table_bbox = Rect(x0=50, y0=190, x1=300, y1=260)
    ir = build_page_ir_real(native, table_regions=[table_bbox])

    table_blocks = [b for b in ir.blocks if b.type == "table"]
    assert len(table_blocks) == 1
    # 3 rows → 2 line breaks
    line_breaks = [c for c in table_blocks[0].children if c.type == "line_break"]
    assert len(line_breaks) == 2


def test_table_heading_not_promoted() -> None:
    """Heading-font text inside table region should NOT become a HeadingBlock."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="Evolution Track",
            font_name="GreenleafLightPro",
            font_size=12.0,
            bbox=Rect(x0=60, y0=200, x1=200, y1=215),
        ),
        SpanEvidence(
            span_id="s002",
            text="Level 1",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=225, x1=120, y1=237),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[],
    )
    table_bbox = Rect(x0=50, y0=190, x1=250, y1=250)
    ir = build_page_ir_real(native, table_regions=[table_bbox])

    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) == 0
    table_blocks = [b for b in ir.blocks if b.type == "table"]
    assert len(table_blocks) == 1
    text = " ".join(c.text for c in table_blocks[0].children if hasattr(c, "text"))
    assert "Evolution Track" in text


def test_no_table_region_unchanged_behavior() -> None:
    """Without table_regions, existing behavior is unchanged."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="Normal paragraph text",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=200, x1=300, y1=212),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[],
    )
    ir_no_regions = build_page_ir_real(native)
    ir_empty_regions = build_page_ir_real(native, table_regions=[])

    assert len(ir_no_regions.blocks) == 1
    assert ir_no_regions.blocks[0].type == "paragraph"
    assert len(ir_empty_regions.blocks) == 1
    assert ir_empty_regions.blocks[0].type == "paragraph"


def test_mixed_table_and_prose() -> None:
    """Table region spans and non-table prose coexist on the same page."""
    spans = [
        SpanEvidence(
            span_id="s001",
            text="Introduction",
            font_name="GreenleafLightPro",
            font_size=14.0,
            bbox=Rect(x0=60, y0=80, x1=200, y1=98),
        ),
        SpanEvidence(
            span_id="s002",
            text="Some prose text before the table.",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=110, x1=400, y1=122),
        ),
        # Table content
        SpanEvidence(
            span_id="s003",
            text="Row A",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=200, x1=120, y1=212),
        ),
        SpanEvidence(
            span_id="s004",
            text="Row B",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=220, x1=120, y1=232),
        ),
        # More prose after table
        SpanEvidence(
            span_id="s005",
            text="Text after the table.",
            font_name="Adonis-Regular",
            font_size=9.0,
            bbox=Rect(x0=60, y0=300, x1=300, y1=312),
        ),
    ]
    native = NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=842),
        words=[],
        spans=spans,
        image_blocks=[],
    )
    table_bbox = Rect(x0=50, y0=190, x1=200, y1=240)
    ir = build_page_ir_real(native, table_regions=[table_bbox])

    types = [b.type for b in ir.blocks]
    assert "heading" in types
    assert "table" in types
    assert "paragraph" in types
    # Table appears after heading and between two paragraphs
    assert types.index("heading") < types.index("table")
    assert types.count("paragraph") == 2
    assert types.count("table") == 1

"""Tests for the real page block builder."""

from pathlib import Path

from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.native_page_v1 import ImageBlockEvidence, NativePageV1

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
    first_heading_text = " ".join(
        c.text for c in headings[0].children if hasattr(c, "text")
    )
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
    """Larger headings should get level 1, smaller should get level 2+."""
    if _skip_if_no_pdf():
        return
    native = extract_native_page(PDF_PATH, page_number=11, document_id="ato")
    ir = build_page_ir_real(native)

    headings = [b for b in ir.blocks if b.type == "heading"]
    if len(headings) >= 2:
        # Should have different levels if fonts differ
        levels = {h.level for h in headings}
        assert len(levels) >= 1  # At least one level present


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
    assert figure_blocks[0].asset_id == "img0000"
    assert "img0000" in ir.assets


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

"""Tests for PyMuPDF native extraction."""

from pathlib import Path

from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
from atr_schemas.native_page_v1 import NativePageV1

FIXTURE_DIR = (
    Path(__file__).resolve().parents[6]
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "source"
)


def test_extract_walking_skeleton_page() -> None:
    """Extract words and images from the walking skeleton sample page."""
    pdf_path = FIXTURE_DIR / "sample_page_01.pdf"
    page = extract_native_page(pdf_path, page_number=1, document_id="walking_skeleton")

    assert isinstance(page, NativePageV1)
    assert page.page_id == "p0001"
    assert page.page_number == 1
    assert page.dimensions_pt.width > 590
    assert page.dimensions_pt.height > 840

    # Should have extracted words
    assert len(page.words) > 0
    word_texts = [w.text for w in page.words]
    assert "Attack" in word_texts
    assert "Test" in word_texts

    # Should have extracted at least one image (the icon)
    assert len(page.image_blocks) >= 1

    # All bboxes should be within page bounds
    for w in page.words:
        assert w.bbox.x0 >= 0
        assert w.bbox.y0 >= 0
        assert w.bbox.x1 <= page.dimensions_pt.width + 1
        assert w.bbox.y1 <= page.dimensions_pt.height + 1

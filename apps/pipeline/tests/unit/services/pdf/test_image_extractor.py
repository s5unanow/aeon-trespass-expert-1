"""Tests for PDF image extraction service."""

from pathlib import Path

from atr_pipeline.services.pdf.image_extractor import ExtractedImage, extract_page_images

PDF_PATH = Path(__file__).resolve().parents[6] / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"


def _skip_if_no_pdf() -> bool:
    return not PDF_PATH.exists()


def test_extracted_image_dataclass() -> None:
    """ExtractedImage fields are accessible."""
    img = ExtractedImage(
        page_number=1,
        image_id="p0001.img0000",
        xref=42,
        width_px=200,
        height_px=300,
        image_bytes=b"\x89PNG",
        extension=".png",
    )
    assert img.page_number == 1
    assert img.image_id == "p0001.img0000"
    assert img.width_px == 200
    assert img.height_px == 300
    assert img.extension == ".png"


def test_extract_page_images_filters_small() -> None:
    """Images below the size threshold should be excluded."""
    if _skip_if_no_pdf():
        return
    # Page 1 (cover) typically has images; extract with a very high threshold
    images = extract_page_images(PDF_PATH, page_number=1, min_width=9999, min_height=9999)
    assert len(images) == 0


def test_extract_page_images_returns_data() -> None:
    """Extracted images should have non-empty bytes and valid extensions."""
    if _skip_if_no_pdf():
        return
    # Use a page known to have images (cover page)
    images = extract_page_images(PDF_PATH, page_number=1)
    # We can't guarantee images on page 1, but if there are any they should be valid
    for img in images:
        assert len(img.image_bytes) > 0
        assert img.extension.startswith(".")
        assert img.width_px >= 50
        assert img.height_px >= 50
        assert img.image_id.startswith("p0001.img")

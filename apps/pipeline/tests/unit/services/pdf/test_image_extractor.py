"""Tests for PDF image extraction service."""

import logging
from pathlib import Path

import fitz
import pytest

from atr_pipeline.services.pdf import image_extractor
from atr_pipeline.services.pdf.image_extractor import ExtractedImage, extract_page_images

PDF_PATH = Path(__file__).resolve().parents[6] / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"

# Small committed fixture (guaranteed present, unlike materials/) with one image.
FIXTURE_PDF = (
    Path(__file__).resolve().parents[6]
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "source"
    / "sample_page_01.pdf"
)


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


def test_extract_image_failure_is_logged_not_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A PyMuPDF failure decoding an image must skip it AND log a WARNING — not
    silently ``continue`` (S5U-1234, NEVER-list: no silent except).
    """
    assert FIXTURE_PDF.exists(), "committed fixture PDF must be present"

    def _raise_extract(self: fitz.Document, xref: int) -> object:
        raise RuntimeError("simulated undecodable image xref")

    monkeypatch.setattr(fitz.Document, "extract_image", _raise_extract)

    with caplog.at_level(logging.WARNING, logger=image_extractor.__name__):
        images = extract_page_images(FIXTURE_PDF, page_number=1)

    # The undecodable image is skipped (no crash) ...
    assert images == []
    # ... but the drop is loud: a WARNING naming the xref was emitted.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING when an image can't be decoded"
    assert any("Skipping image" in r.getMessage() for r in warnings)

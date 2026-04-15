"""Tests for the PaddleOCR layout adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.stages.extract_layout import paddleocr_adapter
from atr_pipeline.stages.extract_layout.paddleocr_adapter import (
    _parse_detection,
    _polygon_to_rect,
    extract_layout_ocr,
)
from atr_schemas.common import PageDimensions
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1


def _page() -> NativePageV1:
    return NativePageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
    )


def _mock_ocr(detections: list[Any]) -> MagicMock:
    """Create a mock PaddleOCR engine returning a single page of detections."""
    ocr = MagicMock()
    ocr.ocr.return_value = [detections] if detections else [[]]
    return ocr


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Reset the lazy singletons between tests."""
    paddleocr_adapter._ocr_instance = None
    paddleocr_adapter._paddleocr_unavailable = False
    yield
    paddleocr_adapter._ocr_instance = None
    paddleocr_adapter._paddleocr_unavailable = False


# -- graceful degradation --


def test_empty_layout_without_image() -> None:
    """No page image → empty LayoutPageV1, no OCR engine touched."""
    result = extract_layout_ocr(_page(), page_image_path=None)
    assert isinstance(result, LayoutPageV1)
    assert result.zones == []
    assert result.ocr_words == []
    assert result.difficulty is None


def test_empty_layout_when_paddleocr_missing() -> None:
    """When PaddleOCR is not installed, returns an empty layout."""
    with patch.object(paddleocr_adapter, "_get_ocr", return_value=None):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"))
    assert result.zones == []
    assert result.ocr_words == []


def test_empty_layout_when_engine_returns_nothing() -> None:
    """Engine returning an empty page produces an empty layout."""
    ocr = _mock_ocr([])
    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"))
    assert result.zones == []
    assert result.ocr_words == []


def test_empty_layout_when_engine_raises() -> None:
    """Exceptions from PaddleOCR inference degrade to an empty layout."""
    ocr = MagicMock()
    ocr.ocr.side_effect = RuntimeError("paddle crash")
    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"))
    assert result.zones == []
    assert result.ocr_words == []


# -- successful extraction --


def test_extracts_zones_and_words_from_detections() -> None:
    """A successful OCR run yields zones, reading order, and word evidence."""
    detections = [
        [[[100, 100], [500, 100], [500, 140], [100, 140]], ("Hello", 0.98)],
        [[[100, 200], [500, 200], [500, 240], [100, 240]], ("World", 0.91)],
    ]
    ocr = _mock_ocr(detections)

    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"), dpi=300)

    assert len(result.zones) == 2
    assert result.zones[0].zone_id == "ocr001"
    assert result.zones[0].kind == "body"
    assert result.zones[0].confidence == pytest.approx(0.98)

    assert len(result.ocr_words) == 2
    assert result.ocr_words[0].text == "Hello"
    assert result.ocr_words[1].text == "World"

    assert result.reading_order_candidates == [["ocr001", "ocr002"]]
    assert result.difficulty is not None


def test_pixel_coordinates_scaled_to_pdf_points() -> None:
    """Polygon pixel coordinates are scaled by 72/dpi to PDF points."""
    detections = [
        [[[300, 600], [900, 600], [900, 700], [300, 700]], ("line", 0.9)],
    ]
    ocr = _mock_ocr(detections)

    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"), dpi=300)

    scale = 72.0 / 300
    zone = result.zones[0]
    assert zone.bbox.x0 == pytest.approx(300 * scale)
    assert zone.bbox.y0 == pytest.approx(600 * scale)
    assert zone.bbox.x1 == pytest.approx(900 * scale)
    assert zone.bbox.y1 == pytest.approx(700 * scale)
    word = result.ocr_words[0]
    assert word.bbox.x0 == pytest.approx(300 * scale)
    assert word.bbox.x1 == pytest.approx(900 * scale)


def test_custom_dpi_changes_coordinates() -> None:
    """Different DPI values scale coordinates inversely."""
    detections = [
        [[[150, 150], [450, 150], [450, 250], [150, 250]], ("line", 0.9)],
    ]
    ocr = _mock_ocr(detections)

    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        r150 = extract_layout_ocr(_page(), Path("/fake/image.png"), dpi=150)
        r300 = extract_layout_ocr(_page(), Path("/fake/image.png"), dpi=300)

    # 150 DPI yields 2x the point value of 300 DPI for the same pixel coordinate
    assert r150.zones[0].bbox.x0 == pytest.approx(r300.zones[0].bbox.x0 * 2)


def test_confidence_is_clamped_and_coerced() -> None:
    """Out-of-range or non-numeric confidence values degrade to safe defaults."""
    detections = [
        [[[10, 10], [20, 10], [20, 20], [10, 20]], ("a", 1.7)],
        [[[30, 30], [40, 30], [40, 40], [30, 40]], ("b", "bogus")],
    ]
    ocr = _mock_ocr(detections)

    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"))

    assert result.zones[0].confidence == pytest.approx(1.0)
    assert result.zones[1].confidence == pytest.approx(0.0)


def test_malformed_detections_are_skipped() -> None:
    """Entries missing polygon or payload fields are dropped."""
    detections = [
        None,  # bogus
        [[[10, 10], [20, 10], [20, 20], [10, 20]], ("good", 0.95)],
        [[], ("empty_poly", 0.9)],
        [[[1, 1], [2, 1], [2, 2], [1, 2]], None],
    ]
    ocr = _mock_ocr(detections)

    with patch.object(paddleocr_adapter, "_get_ocr", return_value=ocr):
        result = extract_layout_ocr(_page(), Path("/fake/image.png"))

    assert len(result.zones) == 1
    assert result.ocr_words[0].text == "good"


def test_degenerate_polygon_is_skipped() -> None:
    """Zero-width or inverted polygons are rejected (Rect would fail validation)."""
    rect = _polygon_to_rect([[100.0, 100.0], [100.0, 100.0], [100.0, 100.0], [100.0, 100.0]], 1.0)
    assert rect is None


def test_parse_detection_returns_none_for_short_entry() -> None:
    """Detection entries with fewer than 2 elements return None."""
    assert _parse_detection([]) is None
    assert _parse_detection([[[1, 1], [2, 2]]]) is None


# -- engine singleton behavior --


def test_missing_paddleocr_caches_unavailable_flag() -> None:
    """Failing to import PaddleOCR flips the cached unavailability flag once."""
    with patch.dict("sys.modules", {"paddleocr": None}):
        # First call tries the import and flips the flag
        assert paddleocr_adapter._get_ocr() is None
        assert paddleocr_adapter._paddleocr_unavailable is True
        # Second call short-circuits on the cached flag
        assert paddleocr_adapter._get_ocr() is None

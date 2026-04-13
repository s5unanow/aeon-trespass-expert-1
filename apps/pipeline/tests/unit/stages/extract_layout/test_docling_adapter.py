"""Tests for the Docling layout adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.stages.extract_layout import docling_adapter
from atr_pipeline.stages.extract_layout.docling_adapter import (
    _LABEL_TO_KIND,
    _run_docling,
    _stub_layout,
    extract_layout_docling,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence


def _page(words: list[WordEvidence] | None = None) -> NativePageV1:
    return NativePageV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=words or [],
    )


def _word(x0: float, y0: float, x1: float, y1: float) -> WordEvidence:
    return WordEvidence(word_id="w1", text="w", bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1))


# -- stub fallback tests --


def test_stub_fallback_no_image() -> None:
    """Without a page image, adapter returns stub layout."""
    result = extract_layout_docling(_page(), page_image_path=None)
    assert isinstance(result, LayoutPageV1)
    assert len(result.zones) == 1
    assert result.zones[0].kind == "body"
    assert result.difficulty is not None


def test_stub_fallback_no_docling() -> None:
    """When Docling is not installed, adapter returns stub layout."""
    with patch.object(docling_adapter, "_get_converter", return_value=None):
        result = extract_layout_docling(_page(), Path("/fake/image.png"))
    assert len(result.zones) == 1
    assert result.zones[0].kind == "body"


def test_stub_layout_uses_page_dimensions() -> None:
    """Stub body zone respects page dimensions with 50pt margins."""
    page = _page()
    result = _stub_layout(page)
    zone = result.zones[0]
    assert zone.bbox.x0 == 50
    assert zone.bbox.y0 == 50
    assert zone.bbox.x1 == pytest.approx(612 - 50)
    assert zone.bbox.y1 == pytest.approx(792 - 50)


def test_stub_layout_includes_difficulty() -> None:
    """Stub fallback still computes real difficulty scoring."""
    words = [_word(50, y * 15, 560, y * 15 + 12) for y in range(5, 50)]
    result = _stub_layout(_page(words))
    assert result.difficulty is not None
    assert result.difficulty.recommended_route == "R1"


# -- Docling integration tests (mocked) --


def _mock_docling_item(
    label: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> SimpleNamespace:
    """Create a mock Docling document item."""
    label_obj = SimpleNamespace(value=label)
    bbox = SimpleNamespace(l=left, t=top, r=right, b=bottom)
    prov = SimpleNamespace(bbox=bbox)
    return SimpleNamespace(label=label_obj, prov=[prov])


def _mock_converter(items: list[SimpleNamespace]) -> MagicMock:
    """Create a mock DocumentConverter returning given items."""
    converter = MagicMock()
    doc = MagicMock()
    doc.iterate_items.return_value = [(item, 0) for item in items]
    result = MagicMock()
    result.document = doc
    converter.convert.return_value = result
    return converter


def test_docling_produces_zones() -> None:
    """Docling items are converted to LayoutZones."""
    items = [
        _mock_docling_item("text", 100, 100, 500, 200),
        _mock_docling_item("figure", 100, 250, 500, 500),
    ]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"), dpi=300)

    assert len(result.zones) == 2
    assert result.zones[0].kind == "body"
    assert result.zones[0].zone_id == "z001"
    assert result.zones[1].kind == "figure"
    assert result.zones[1].zone_id == "z002"


def test_docling_coordinate_conversion() -> None:
    """Pixel coordinates are scaled to PDF points (72/dpi)."""
    items = [_mock_docling_item("text", 300, 600, 900, 1200)]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"), dpi=300)

    zone = result.zones[0]
    scale = 72.0 / 300
    assert zone.bbox.x0 == pytest.approx(300 * scale)
    assert zone.bbox.y0 == pytest.approx(600 * scale)
    assert zone.bbox.x1 == pytest.approx(900 * scale)
    assert zone.bbox.y1 == pytest.approx(1200 * scale)


def test_docling_custom_dpi() -> None:
    """Different DPI produces different point coordinates."""
    items = [_mock_docling_item("text", 150, 150, 450, 450)]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        r150 = extract_layout_docling(_page(), Path("/fake/img.png"), dpi=150)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        r300 = extract_layout_docling(_page(), Path("/fake/img.png"), dpi=300)

    # At 150 DPI, coordinates are 2x larger in points than at 300 DPI
    assert r150.zones[0].bbox.x0 == pytest.approx(r300.zones[0].bbox.x0 * 2)


def test_docling_reading_order() -> None:
    """Reading order is built from Docling iteration order."""
    items = [
        _mock_docling_item("title", 100, 50, 500, 100),
        _mock_docling_item("text", 100, 120, 500, 300),
        _mock_docling_item("text", 100, 320, 500, 500),
    ]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"))

    assert len(result.reading_order_candidates) == 1
    assert result.reading_order_candidates[0] == ["z001", "z002", "z003"]


def test_docling_empty_result_falls_back() -> None:
    """If Docling returns no items, adapter falls back to stub."""
    converter = _mock_converter([])

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"))

    assert len(result.zones) == 1
    assert result.zones[0].kind == "body"


def test_docling_skips_items_without_provenance() -> None:
    """Items lacking provenance data are skipped."""
    good = _mock_docling_item("text", 100, 100, 500, 200)
    no_prov = SimpleNamespace(label=SimpleNamespace(value="text"), prov=[])
    converter = _mock_converter([good, no_prov])

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"))

    assert len(result.zones) == 1


def test_docling_conversion_error_returns_empty() -> None:
    """If Docling raises during conversion, _run_docling returns empty."""
    converter = MagicMock()
    converter.convert.side_effect = RuntimeError("model crash")

    zones, reading_order = _run_docling(converter, Path("/fake.png"), _page(), 300)
    assert zones == []
    assert reading_order == []


def test_docling_includes_difficulty() -> None:
    """Docling-extracted zones are scored by the difficulty scorer."""
    words = [_word(50, y * 15, 560, y * 15 + 12) for y in range(5, 50)]
    items = [_mock_docling_item("text", 50, 50, 560, 700)]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(words), Path("/fake/img.png"))

    assert result.difficulty is not None
    assert result.difficulty.page_id == "p0001"


def test_label_mapping_covers_common_types() -> None:
    """All major Docling label types have a mapping."""
    expected = {"text", "title", "table", "figure", "caption", "section_header"}
    assert expected.issubset(set(_LABEL_TO_KIND.keys()))


def test_unknown_label_defaults_to_body() -> None:
    """Unknown Docling labels map to 'body'."""
    items = [_mock_docling_item("unknown_type_xyz", 100, 100, 200, 200)]
    converter = _mock_converter(items)

    with patch.object(docling_adapter, "_get_converter", return_value=converter):
        result = extract_layout_docling(_page(), Path("/fake/img.png"))

    assert result.zones[0].kind == "body"

"""Tests for vector evidence extraction — including null-width handling."""

from __future__ import annotations

from unittest.mock import MagicMock

from atr_pipeline.stages.extract_native.evidence_text import clamp_rect_to_page
from atr_pipeline.stages.extract_native.evidence_vectors import (
    extract_image_evidence,
    extract_vector_evidence,
)
from atr_schemas.common import PageDimensions, Rect


def _make_page(drawings: list[dict[str, object]]) -> MagicMock:
    page = MagicMock()
    page.get_drawings.return_value = drawings
    return page


def _dims() -> PageDimensions:
    return PageDimensions(width=612.0, height=792.0)


def _make_rect() -> MagicMock:
    r = MagicMock()
    r.x0, r.y0, r.x1, r.y1 = 10.0, 20.0, 100.0, 50.0
    return r


def test_null_width_normalized_to_zero() -> None:
    """PyMuPDF can return width=None; should not cause a ValidationError."""
    drawing = {
        "rect": _make_rect(),
        "items": [("l",)],
        "color": None,
        "fill": None,
        "width": None,
    }
    paths, _ = extract_vector_evidence(_make_page([drawing]), _dims())
    assert len(paths) == 1
    assert paths[0].line_width == 0.0


def test_missing_width_key_defaults_to_zero() -> None:
    """When width key is absent, should default to 0.0."""
    drawing = {
        "rect": _make_rect(),
        "items": [],
        "color": None,
        "fill": None,
    }
    paths, _ = extract_vector_evidence(_make_page([drawing]), _dims())
    assert len(paths) == 1
    assert paths[0].line_width == 0.0


def test_explicit_width_preserved() -> None:
    """A normal float width should pass through unchanged."""
    drawing = {
        "rect": _make_rect(),
        "items": [],
        "color": None,
        "fill": None,
        "width": 1.5,
    }
    paths, _ = extract_vector_evidence(_make_page([drawing]), _dims())
    assert len(paths) == 1
    assert paths[0].line_width == 1.5


def test_zero_width_preserved() -> None:
    """Explicit 0.0 width should remain 0.0 (not confused with None)."""
    drawing = {
        "rect": _make_rect(),
        "items": [],
        "color": None,
        "fill": None,
        "width": 0.0,
    }
    paths, _ = extract_vector_evidence(_make_page([drawing]), _dims())
    assert len(paths) == 1
    assert paths[0].line_width == 0.0


# --- bbox clamping helper ---


def test_clamp_in_bounds_rect_unchanged() -> None:
    dims = _dims()
    rect = Rect(x0=10.0, y0=20.0, x1=100.0, y1=200.0)
    clamped = clamp_rect_to_page(rect, dims)
    assert (clamped.x0, clamped.y0, clamped.x1, clamped.y1) == (10.0, 20.0, 100.0, 200.0)


def test_clamp_edge_of_page_preserved_exactly() -> None:
    """A rect flush with the page edge must pass through without rounding."""
    dims = _dims()
    rect = Rect(x0=0.0, y0=0.0, x1=dims.width, y1=dims.height)
    clamped = clamp_rect_to_page(rect, dims)
    assert clamped.x0 == 0.0 and clamped.y0 == 0.0
    assert clamped.x1 == dims.width and clamped.y1 == dims.height


def test_clamp_negative_coords_pulled_to_zero() -> None:
    rect = Rect(x0=-5.0, y0=-10.0, x1=100.0, y1=200.0)
    clamped = clamp_rect_to_page(rect, _dims())
    assert clamped.x0 == 0.0 and clamped.y0 == 0.0
    assert clamped.x1 == 100.0 and clamped.y1 == 200.0


def test_clamp_overrun_coords_pulled_to_page() -> None:
    dims = _dims()
    rect = Rect(x0=10.0, y0=20.0, x1=dims.width + 15.0, y1=dims.height + 7.0)
    clamped = clamp_rect_to_page(rect, dims)
    assert clamped.x1 == dims.width and clamped.y1 == dims.height


# --- vector evidence bbox clamping ---


def _rect_mock(x0: float, y0: float, x1: float, y1: float) -> MagicMock:
    r = MagicMock()
    r.x0, r.y0, r.x1, r.y1 = x0, y0, x1, y1
    return r


def _drawing(x0: float, y0: float, x1: float, y1: float) -> dict[str, object]:
    return {
        "rect": _rect_mock(x0, y0, x1, y1),
        "items": [("l",)],
        "color": None,
        "fill": None,
        "width": 0.5,
    }


def test_vector_path_overrun_bbox_clamped_to_page() -> None:
    """Vector path rects extending past the MediaBox are clamped, not dropped."""
    dims = _dims()
    drawings = [_drawing(10.0, 20.0, dims.width + 12.0, dims.height + 5.0)]
    paths, _ = extract_vector_evidence(_make_page(drawings), dims)
    assert len(paths) == 1
    bbox = paths[0].bbox
    assert bbox.x1 == dims.width
    assert bbox.y1 == dims.height
    assert bbox.x0 == 10.0 and bbox.y0 == 20.0


def test_vector_path_negative_coords_clamped_to_zero() -> None:
    dims = _dims()
    drawings = [_drawing(-8.0, -4.0, 200.0, 300.0)]
    paths, _ = extract_vector_evidence(_make_page(drawings), dims)
    assert len(paths) == 1
    assert paths[0].bbox.x0 == 0.0
    assert paths[0].bbox.y0 == 0.0


def test_vector_path_entirely_off_page_is_dropped() -> None:
    """A path wholly beyond the MediaBox collapses on clamp and must be dropped."""
    dims = _dims()
    drawings = [
        _drawing(dims.width + 10.0, dims.height + 5.0, dims.width + 50.0, dims.height + 25.0)
    ]
    paths, _ = extract_vector_evidence(_make_page(drawings), dims)
    assert paths == []


def test_vector_path_zero_width_rule_preserved() -> None:
    """Zero-width vertical rules (common in PDFs) must not be treated as degenerate."""
    dims = _dims()
    drawings = [_drawing(100.0, 50.0, 100.0, 400.0)]
    paths, _ = extract_vector_evidence(_make_page(drawings), dims)
    assert len(paths) == 1
    assert paths[0].bbox.x0 == paths[0].bbox.x1 == 100.0


def test_vector_cluster_bbox_stays_within_page() -> None:
    """Clusters union already-clamped path bboxes, so they stay in page bounds."""
    dims = _dims()
    drawings = [
        _drawing(-5.0, 10.0, 80.0, 60.0),
        _drawing(70.0, 20.0, dims.width + 20.0, 80.0),
    ]
    _, clusters = extract_vector_evidence(_make_page(drawings), dims)
    assert len(clusters) == 1
    bbox = clusters[0].bbox
    assert bbox.x0 == 0.0
    assert bbox.x1 == dims.width
    assert bbox.y0 == 10.0
    assert bbox.y1 == 80.0


# --- image evidence bbox clamping ---


def _make_image_page(
    rect: MagicMock,
    img_info: tuple[int | str, ...],
) -> tuple[MagicMock, MagicMock]:
    page = MagicMock()
    page.get_images.return_value = [img_info]
    page.get_image_rects.return_value = [rect]
    doc = MagicMock()
    doc.extract_image.return_value = {"image": b""}
    return page, doc


def test_image_overrun_bbox_clamped() -> None:
    dims = _dims()
    rect = _rect_mock(-2.0, -1.0, dims.width + 5.0, dims.height + 9.0)
    img_info = (17, 0, 100, 200, 0, "DeviceRGB")
    page, doc = _make_image_page(rect, img_info)
    images = extract_image_evidence(page, doc, dims)
    assert len(images) == 1
    bbox = images[0].bbox
    assert bbox.x0 == 0.0 and bbox.y0 == 0.0
    assert bbox.x1 == dims.width and bbox.y1 == dims.height


def test_image_entirely_off_page_dropped() -> None:
    dims = _dims()
    rect = _rect_mock(dims.width + 2.0, 0.0, dims.width + 20.0, 50.0)
    img_info = (17, 0, 100, 200, 0, "DeviceRGB")
    page, doc = _make_image_page(rect, img_info)
    assert extract_image_evidence(page, doc, dims) == []

"""Tests for vector evidence extraction — including null-width handling."""

from __future__ import annotations

from unittest.mock import MagicMock

from atr_schemas.common import PageDimensions

from atr_pipeline.stages.extract_native.evidence_vectors import extract_vector_evidence


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

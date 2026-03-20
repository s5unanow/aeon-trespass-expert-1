"""Tests for furniture detection — cross-page repetition analysis."""

from __future__ import annotations

from atr_pipeline.stages.structure.furniture import (
    FurnitureMap,
    detect_furniture,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence


def _span(
    span_id: str,
    text: str,
    y0: float,
    y1: float | None = None,
) -> SpanEvidence:
    return SpanEvidence(
        span_id=span_id,
        text=text,
        bbox=Rect(x0=50, y0=y0, x1=200, y1=y1 or y0 + 12),
        font_name="Adonis-Regular",
        font_size=10.0,
    )


def _page(
    page_id: str,
    spans: list[SpanEvidence],
    page_height: float = 792.0,
) -> NativePageV1:
    return NativePageV1(
        document_id="test",
        page_id=page_id,
        page_number=int(page_id[1:]),
        dimensions_pt=PageDimensions(width=612.0, height=page_height),
        spans=spans,
    )


class TestFurnitureMap:
    def test_empty_map(self) -> None:
        fm = FurnitureMap()
        assert not fm.has_furniture
        assert not fm.is_furniture_span("s1")

    def test_map_with_spans(self) -> None:
        fm = FurnitureMap(stripped_span_ids=["s1", "s2"])
        assert fm.has_furniture
        assert fm.is_furniture_span("s1")
        assert not fm.is_furniture_span("s3")


class TestDetectFurniture:
    def test_single_page_returns_empty(self) -> None:
        page = _page("p0001", [_span("s1", "body text", 100)])
        result = detect_furniture([page])
        assert not result.has_furniture

    def test_detects_repeated_header(self) -> None:
        """Text in top zone repeating on all pages is detected as furniture."""
        pages = [
            _page(
                f"p{i:04d}",
                [
                    _span(f"s{i}_h", "AEON TRESPASS", 20),
                    _span(f"s{i}_b", f"Body text page {i}", 200),
                ],
            )
            for i in range(1, 5)
        ]
        result = detect_furniture(pages)
        assert result.has_furniture
        assert len(result.repeated_regions) == 1
        assert result.repeated_regions[0].zone == "top"
        assert "aeon trespass" in result.repeated_regions[0].text
        # All 4 header span IDs should be stripped
        assert len(result.stripped_span_ids) == 4

    def test_detects_repeated_footer(self) -> None:
        """Text in bottom zone repeating on all pages is detected."""
        pages = [
            _page(
                f"p{i:04d}",
                [
                    _span(f"s{i}_b", f"Body text {i}", 200),
                    _span(f"s{i}_f", "Copyright 2026", 760),
                ],
            )
            for i in range(1, 5)
        ]
        result = detect_furniture(pages)
        assert result.has_furniture
        assert any(r.zone == "bottom" for r in result.repeated_regions)

    def test_ignores_body_text(self) -> None:
        """Text in body zone is not detected as furniture."""
        pages = [
            _page(
                f"p{i:04d}",
                [_span(f"s{i}", "Repeated body text", 200)],
            )
            for i in range(1, 5)
        ]
        result = detect_furniture(pages)
        assert not result.has_furniture

    def test_ignores_page_numbers(self) -> None:
        """Pure page numbers are not flagged as furniture."""
        pages = [
            _page(
                f"p{i:04d}",
                [
                    _span(f"s{i}_n", str(i), 770),
                    _span(f"s{i}_b", f"Body {i}", 200),
                ],
            )
            for i in range(1, 5)
        ]
        result = detect_furniture(pages)
        assert not result.has_furniture

    def test_threshold_50_percent(self) -> None:
        """Text must appear on >50% of pages to be furniture."""
        pages = [
            _page("p0001", [_span("s1", "Header", 20)]),
            _page("p0002", [_span("s2", "Header", 20)]),
            _page("p0003", [_span("s3", "Different", 20)]),
            _page("p0004", [_span("s4", "Also different", 20)]),
        ]
        result = detect_furniture(pages)
        # "Header" appears on 2 of 4 pages (50%) — at threshold
        assert result.has_furniture
        assert len(result.stripped_span_ids) == 2

    def test_below_threshold_not_detected(self) -> None:
        """Text on <50% of pages is not furniture."""
        pages = [
            _page("p0001", [_span("s1", "Rare header", 20)]),
            _page("p0002", [_span("s2", "Other text", 20)]),
            _page("p0003", [_span("s3", "Other text 2", 20)]),
            _page("p0004", [_span("s4", "Other text 3", 20)]),
            _page("p0005", [_span("s5", "Other text 4", 20)]),
        ]
        result = detect_furniture(pages)
        # "Rare header" on 1 of 5 pages (20%) — below threshold
        assert not result.is_furniture_span("s1")

    def test_multiple_regions(self) -> None:
        """Detects both header and footer furniture simultaneously."""
        pages = [
            _page(
                f"p{i:04d}",
                [
                    _span(f"s{i}_h", "RULES REFERENCE", 15),
                    _span(f"s{i}_b", f"Content {i}", 200),
                    _span(f"s{i}_f", "v1.1", 760),
                ],
            )
            for i in range(1, 5)
        ]
        result = detect_furniture(pages)
        assert len(result.repeated_regions) == 2
        zones = {r.zone for r in result.repeated_regions}
        assert zones == {"top", "bottom"}

"""Tests for difficulty scoring."""

from __future__ import annotations

from atr_pipeline.stages.extract_layout.difficulty_scorer import compute_difficulty
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.layout_page_v1 import LayoutZone
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence


def _page(words: list[WordEvidence] | None = None) -> NativePageV1:
    return NativePageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        dimensions_pt=PageDimensions(width=612, height=792),
        words=words or [],
    )


def _word(x0: float, y0: float, x1: float, y1: float, text: str = "w") -> WordEvidence:
    return WordEvidence(
        word_id="w1",
        text=text,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
    )


def test_empty_page_is_hard() -> None:
    """A page with no words should be flagged as hard."""
    d = compute_difficulty(_page(), [])
    assert d.hard_page is True
    assert d.native_text_coverage == 0.0
    assert d.recommended_route != "R1"


def test_single_column_normal_coverage() -> None:
    """Page with enough text spread across the page should be easy."""
    # Words spanning the full width, covering significant page area
    words = [_word(50, y * 15, 560, y * 15 + 12) for y in range(5, 50)]
    d = compute_difficulty(_page(words), [])
    assert d.hard_page is False
    assert d.column_count == 1
    assert d.recommended_route == "R1"


def test_multicolumn_detection() -> None:
    """Words split into two clusters with a gap should detect 2 columns."""
    left_words = [_word(50, y * 20, 250, y * 20 + 12) for y in range(5, 30)]
    right_words = [_word(350, y * 20, 550, y * 20 + 12) for y in range(5, 30)]
    d = compute_difficulty(_page(left_words + right_words), [])
    assert d.column_count == 2
    assert d.hard_page is True
    assert d.recommended_route == "R2"


def test_zone_overlap_ratio() -> None:
    """Overlapping zones should produce nonzero overlap ratio."""
    z1 = LayoutZone(zone_id="z1", kind="body", bbox=Rect(x0=0, y0=0, x1=300, y1=400))
    z2 = LayoutZone(zone_id="z2", kind="sidebar", bbox=Rect(x0=200, y0=0, x1=500, y1=400))
    d = compute_difficulty(_page([_word(50, 50, 100, 60)] * 20), [z1, z2])
    assert d.zone_overlap_ratio > 0.0


def test_nonoverlapping_zones() -> None:
    """Non-overlapping zones should have zero overlap."""
    z1 = LayoutZone(zone_id="z1", kind="body", bbox=Rect(x0=0, y0=0, x1=200, y1=400))
    z2 = LayoutZone(zone_id="z2", kind="sidebar", bbox=Rect(x0=300, y0=0, x1=500, y1=400))
    d = compute_difficulty(_page([_word(50, 50, 100, 60)] * 20), [z1, z2])
    assert d.zone_overlap_ratio == 0.0

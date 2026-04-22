"""Tests for column-aware block reordering (S5U-700).

These tests cover the new fallback added to ``reorder_blocks_by_regions``
when blocks pile into a single wide region because upstream region
segmentation failed to split columns.

Red-before confirmation: at main @ bdb4b1b these tests fail — the
original semantic_resolver.py sort key was ``(region_pos, y0, orig_idx)``
without a column term, so blocks interleaved by y0. See S5U-700 plan
§"Root-cause layering" for the p0042 / p0046 / p0048 retro.
"""

from __future__ import annotations

from atr_pipeline.stages.structure.block_reorder import (
    _detect_block_gutter,
    reorder_blocks_by_regions,
)
from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.page_ir_v1 import ParagraphBlock, TextInline
from atr_schemas.resolved_page_v1 import ResolvedRegion


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _norm(r: Rect, w: float = 595.0, h: float = 842.0) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, r.x0 / w)),
        y0=max(0.0, min(1.0, r.y0 / h)),
        x1=max(0.0, min(1.0, r.x1 / w)),
        y1=max(0.0, min(1.0, r.y1 / h)),
    )


def _para(bid: str, x0: float, y0: float, x1: float, y1: float) -> ParagraphBlock:
    return ParagraphBlock(block_id=bid, bbox=_rect(x0, y0, x1, y1), children=[TextInline(text="x")])


def _region(
    rid: str, kind: RegionKind, x0: float, y0: float, x1: float, y1: float
) -> ResolvedRegion:
    bbox = _rect(x0, y0, x1, y1)
    return ResolvedRegion(region_id=rid, kind=kind, bbox=bbox, norm_bbox=_norm(bbox))


class TestColumnAwareFallback:
    """When upstream collapsed two columns into one wide region."""

    def test_two_columns_in_one_wide_region_split(self) -> None:
        """S5U-700 p0042 shape: one FULL_WIDTH region containing two columns.

        Without the fallback, blocks interleave by y0:
          left-y100, right-y110, left-y120, right-y130...
        With the fallback, they read left-first then right-first.
        """
        blocks = [
            _para("left_top", 50, 100, 280, 120),
            _para("right_top", 320, 110, 560, 130),
            _para("left_mid", 50, 200, 280, 220),
            _para("right_mid", 320, 210, 560, 230),
            _para("left_bot", 50, 300, 280, 320),
            _para("right_bot", 320, 310, 560, 330),
        ]
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842),
        ]
        result = reorder_blocks_by_regions(blocks, regions, ["r001"])
        ids = [b.block_id for b in result]
        # Left column precedes right column, each sorted top-to-bottom.
        assert ids == [
            "left_top",
            "left_mid",
            "left_bot",
            "right_top",
            "right_mid",
            "right_bot",
        ]

    def test_single_column_in_wide_region_preserved(self) -> None:
        """Degenerate single-column page: no gutter detected, sort by y0 only."""
        blocks = [
            _para("b1", 50, 300, 560, 320),
            _para("b2", 50, 100, 560, 120),
            _para("b3", 50, 200, 560, 220),
            _para("b4", 50, 400, 560, 420),
        ]
        regions = [_region("r001", RegionKind.BODY, 40, 90, 570, 430)]
        result = reorder_blocks_by_regions(blocks, regions, ["r001"])
        ids = [b.block_id for b in result]
        assert ids == ["b2", "b3", "b1", "b4"]

    def test_existing_two_region_layout_unchanged(self) -> None:
        """If region_graph already produced separate body regions, respect them."""
        left_col = [_para(f"l{i}", 50, 100 + i * 30, 280, 120 + i * 30) for i in range(4)]
        right_col = [_para(f"r{i}", 320, 100 + i * 30, 560, 120 + i * 30) for i in range(4)]
        regions = [
            _region("r001", RegionKind.BODY, 40, 90, 290, 230),
            _region("r002", RegionKind.BODY, 310, 90, 570, 230),
        ]
        result = reorder_blocks_by_regions(
            list(left_col) + list(right_col), regions, ["r001", "r002"]
        )
        ids = [b.block_id for b in result]
        assert ids == ["l0", "l1", "l2", "l3", "r0", "r1", "r2", "r3"]

    def test_too_few_blocks_no_split(self) -> None:
        """Below the block-count floor (<4), do not trigger fallback."""
        blocks = [
            _para("left", 50, 100, 280, 120),
            _para("right", 320, 110, 560, 130),
            _para("centre", 100, 200, 500, 220),
        ]
        regions = [_region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842)]
        result = reorder_blocks_by_regions(blocks, regions, ["r001"])
        ids = [b.block_id for b in result]
        # Pure y0 order — no column split
        assert ids == ["left", "right", "centre"]


class TestDetectBlockGutter:
    """Direct test of the gutter-detection primitive."""

    def test_two_columns_gap_detected(self) -> None:
        region = _region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842)
        blocks = [
            _para("l1", 50, 100, 280, 120),
            _para("l2", 50, 200, 280, 220),
            _para("r1", 320, 100, 560, 120),
            _para("r2", 320, 200, 560, 220),
        ]
        gutter = _detect_block_gutter(blocks, region)
        assert gutter is not None
        assert 240 < gutter < 330  # between left-centre ~165 and right-centre ~440

    def test_single_column_returns_none(self) -> None:
        region = _region("r001", RegionKind.BODY, 40, 90, 570, 230)
        blocks = [
            _para("b1", 50, 100, 560, 120),
            _para("b2", 50, 150, 560, 170),
            _para("b3", 50, 200, 560, 220),
        ]
        assert _detect_block_gutter(blocks, region) is None

    def test_single_stray_outlier_does_not_split(self) -> None:
        """One far-right block should not count as a second column."""
        region = _region("r001", RegionKind.BODY, 0, 0, 595, 842)
        blocks = [_para(f"b{i}", 50, 100 + i * 30, 280, 120 + i * 30) for i in range(4)]
        blocks.append(_para("outlier", 500, 100, 560, 120))
        gutter = _detect_block_gutter(blocks, region)
        # Right side only has 1 block — gutter rejected.
        assert gutter is None

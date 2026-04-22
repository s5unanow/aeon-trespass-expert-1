"""Best-fit containment tests for ``_assign_blocks_to_regions`` (S5U-700).

Red-before confirmation: at main @ bdb4b1b the original implementation
iterated regions in list order and broke on first containment match.
When a page-spanning FULL_WIDTH region preceded real column regions
(or when no column split happened and only FULL_WIDTH existed), every
block got assigned to FULL_WIDTH, collapsing the two-column reading
order. These tests fail at that commit because the first-match semantics
will pick FULL_WIDTH over the narrower body/sidebar region.
"""

from __future__ import annotations

from atr_pipeline.stages.structure.semantic_resolver import _assign_blocks_to_regions
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


class TestBestFitAssignment:
    def test_content_region_preferred_over_full_width(self) -> None:
        """A block inside both a BODY region and a FULL_WIDTH region goes to BODY."""
        block = _para("b1", 50, 100, 280, 120)
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842),
            _region("r002", RegionKind.BODY, 40, 90, 290, 230),
        ]
        # Even when FULL_WIDTH is listed FIRST, best-fit must pick body.
        assert _assign_blocks_to_regions([block], regions) == {"b1": "r002"}

    def test_smaller_content_region_wins_when_nested(self) -> None:
        """Two content regions contain the block → the smaller one wins."""
        block = _para("b1", 100, 150, 200, 180)
        regions = [
            _region("r001", RegionKind.BODY, 40, 90, 560, 400),
            _region("r002", RegionKind.CALLOUT_AREA, 90, 140, 250, 200),
        ]
        # Callout is content-kind, smaller, should win
        assert _assign_blocks_to_regions([block], regions) == {"b1": "r002"}

    def test_header_only_falls_back_to_header(self) -> None:
        """When the only containing region is HEADER, the block still maps there."""
        block = _para("b1", 50, 35, 200, 50)
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842),
            _region("r002", RegionKind.HEADER, 40, 30, 560, 60),
        ]
        # Both are non-content. Smaller (header) wins over full_width.
        assert _assign_blocks_to_regions([block], regions) == {"b1": "r002"}

    def test_no_containment_produces_empty(self) -> None:
        block = _para("b1", 50, 100, 200, 120)
        regions = [_region("r001", RegionKind.BODY, 400, 400, 500, 500)]
        assert _assign_blocks_to_regions([block], regions) == {}

    def test_full_width_used_only_as_last_resort(self) -> None:
        """A block that fits only in FULL_WIDTH still maps there (not lost)."""
        block = _para("b1", 300, 500, 350, 520)
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 595, 842),
            _region("r002", RegionKind.BODY, 40, 90, 290, 230),  # doesn't contain block
        ]
        assert _assign_blocks_to_regions([block], regions) == {"b1": "r001"}

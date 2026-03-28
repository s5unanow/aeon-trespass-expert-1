"""Tests for block-level diagram noise filters."""

from __future__ import annotations

from atr_pipeline.stages.structure.block_filter import (
    filter_figure_area_blocks,
    filter_heading_clusters,
)
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.page_ir_v1 import (
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.resolved_page_v1 import ResolvedRegion

_DIMS = PageDimensions(width=612.0, height=792.0)


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _norm(r: Rect) -> NormRect:
    return NormRect(
        x0=r.x0 / _DIMS.width,
        y0=r.y0 / _DIMS.height,
        x1=r.x1 / _DIMS.width,
        y1=r.y1 / _DIMS.height,
    )


def _region(
    rid: str, kind: RegionKind, x0: float, y0: float, x1: float, y1: float
) -> ResolvedRegion:
    bbox = _rect(x0, y0, x1, y1)
    return ResolvedRegion(region_id=rid, kind=kind, bbox=bbox, norm_bbox=_norm(bbox))


def _para(
    bid: str, x0: float, y0: float, x1: float, y1: float, text: str = "Sample"
) -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid, bbox=_rect(x0, y0, x1, y1), children=[TextInline(text=text)]
    )


def _heading(bid: str, x0: float, y0: float, x1: float, y1: float, text: str = "H") -> HeadingBlock:
    return HeadingBlock(
        block_id=bid, bbox=_rect(x0, y0, x1, y1), level=1, children=[TextInline(text=text)]
    )


def _figure(bid: str, x0: float, y0: float, x1: float, y1: float) -> FigureBlock:
    return FigureBlock(block_id=bid, bbox=_rect(x0, y0, x1, y1), asset_id="asset_001")


# ── filter_figure_area_blocks ──


class TestFilterFigureAreaBlocks:
    def test_paragraph_in_figure_area_removed(self) -> None:
        para = _para("b1", 50, 100, 200, 120, text="3")
        regions = [_region("r001", RegionKind.FIGURE_AREA, 40, 90, 210, 130)]
        result = filter_figure_area_blocks([para], {"b1": "r001"}, regions)
        assert result == []

    def test_heading_in_figure_area_removed(self) -> None:
        heading = _heading("b1", 50, 100, 200, 120, text="1")
        regions = [_region("r001", RegionKind.FIGURE_AREA, 40, 90, 210, 130)]
        result = filter_figure_area_blocks([heading], {"b1": "r001"}, regions)
        assert result == []

    def test_figure_block_in_figure_area_kept(self) -> None:
        fig = _figure("b1", 50, 100, 400, 300)
        regions = [_region("r001", RegionKind.FIGURE_AREA, 40, 90, 410, 310)]
        result = filter_figure_area_blocks([fig], {"b1": "r001"}, regions)
        assert len(result) == 1

    def test_caption_in_figure_area_kept(self) -> None:
        caption = CaptionBlock(
            block_id="b1",
            bbox=_rect(50, 310, 400, 325),
            figure_block_id="fig1",
            children=[TextInline(text="Figure 1")],
        )
        regions = [_region("r001", RegionKind.FIGURE_AREA, 40, 90, 410, 330)]
        result = filter_figure_area_blocks([caption], {"b1": "r001"}, regions)
        assert len(result) == 1

    def test_paragraph_in_body_area_kept(self) -> None:
        para = _para("b1", 50, 100, 200, 120, text="Body text")
        regions = [_region("r001", RegionKind.BODY, 40, 90, 210, 130)]
        result = filter_figure_area_blocks([para], {"b1": "r001"}, regions)
        assert len(result) == 1

    def test_no_figure_areas_noop(self) -> None:
        para = _para("b1", 50, 100, 200, 120)
        regions = [_region("r001", RegionKind.BODY, 40, 90, 210, 130)]
        result = filter_figure_area_blocks([para], {"b1": "r001"}, regions)
        assert result == [para]

    def test_mixed_blocks_across_regions(self) -> None:
        body_para = _para("b1", 50, 100, 200, 120, text="Body text")
        fig_para = _para("b2", 300, 100, 500, 120, text="2")
        fig = _figure("b3", 300, 150, 500, 300)
        regions = [
            _region("r001", RegionKind.BODY, 40, 90, 210, 130),
            _region("r002", RegionKind.FIGURE_AREA, 290, 90, 510, 310),
        ]
        result = filter_figure_area_blocks(
            [body_para, fig_para, fig],
            {"b1": "r001", "b2": "r002", "b3": "r002"},
            regions,
        )
        assert len(result) == 2
        assert result[0].block_id == "b1"
        assert result[1].block_id == "b3"


# ── filter_heading_clusters ──


class TestFilterHeadingClusters:
    def test_three_short_headings_removed(self) -> None:
        blocks = [
            _heading("b1", 50, 100, 100, 110, text="T0"),
            _heading("b2", 50, 115, 100, 125, text="T1"),
            _heading("b3", 50, 130, 100, 140, text="T2"),
        ]
        result = filter_heading_clusters(blocks)
        assert result == []

    def test_two_short_headings_kept(self) -> None:
        blocks = [
            _heading("b1", 50, 100, 100, 110, text="T0"),
            _heading("b2", 50, 115, 100, 125, text="T1"),
        ]
        result = filter_heading_clusters(blocks)
        assert len(result) == 2

    def test_long_heading_text_not_filtered(self) -> None:
        blocks = [
            _heading("b1", 50, 100, 400, 110, text="Campaign Basics"),
            _heading("b2", 50, 200, 400, 210, text="The Argo"),
            _heading("b3", 50, 300, 400, 310, text="Timeline"),
        ]
        result = filter_heading_clusters(blocks)
        assert len(result) == 3

    def test_cluster_surrounded_by_paragraphs(self) -> None:
        blocks = [
            _para("p1", 50, 50, 400, 80, text="Body text"),
            _heading("b1", 50, 100, 100, 110, text="x"),
            _heading("b2", 50, 115, 100, 125, text="x"),
            _heading("b3", 50, 130, 100, 140, text="x"),
            _heading("b4", 50, 145, 100, 155, text="x"),
            _para("p2", 50, 200, 400, 230, text="More body text"),
        ]
        result = filter_heading_clusters(blocks)
        ids = [b.block_id for b in result]
        assert "p1" in ids
        assert "p2" in ids
        assert "b1" not in ids
        assert "b4" not in ids

    def test_cluster_interrupted_by_paragraph_kept(self) -> None:
        blocks = [
            _heading("b1", 50, 100, 100, 110, text="T0"),
            _heading("b2", 50, 115, 100, 125, text="T1"),
            _para("p1", 50, 130, 400, 145, text="text"),
            _heading("b3", 50, 150, 100, 160, text="T2"),
            _heading("b4", 50, 165, 100, 175, text="T3"),
        ]
        result = filter_heading_clusters(blocks)
        assert len(result) == 5  # No run >= 3, all kept

    def test_empty_blocks(self) -> None:
        assert filter_heading_clusters([]) == []

    def test_non_heading_blocks_untouched(self) -> None:
        blocks = [
            _para("p1", 50, 100, 200, 110, text="A"),
            _para("p2", 50, 115, 200, 125, text="B"),
            _para("p3", 50, 130, 200, 140, text="C"),
        ]
        result = filter_heading_clusters(blocks)
        assert len(result) == 3

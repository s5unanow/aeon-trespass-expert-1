"""Tests for reading-order graph computation."""

from __future__ import annotations

from atr_pipeline.stages.structure.reading_order import compute_reading_order
from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import AnchorEdgeKind, RegionKind
from atr_schemas.resolved_page_v1 import ResolvedRegion


def _region(
    rid: str,
    kind: RegionKind,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    confidence: float = 0.9,
) -> ResolvedRegion:
    return ResolvedRegion(
        region_id=rid,
        kind=kind,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
        norm_bbox=NormRect(x0=0, y0=0, x1=1, y1=1),
        confidence=confidence,
    )


class TestEmptyInput:
    def test_no_regions_returns_empty(self) -> None:
        result = compute_reading_order([])
        assert result.main_flow_order == []
        assert result.anchor_edges == []
        assert result.confidence == 1.0

    def test_only_furniture_returns_empty(self) -> None:
        regions = [
            _region("r001", RegionKind.HEADER, 0, 0, 612, 50),
            _region("r002", RegionKind.FOOTER, 0, 750, 612, 792),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == []
        assert result.anchor_edges == []


class TestSingleColumn:
    def test_single_body_region(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 500, 700),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001"]
        assert result.anchor_edges == []
        assert result.confidence == 1.0

    def test_stacked_body_regions_top_to_bottom(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 500, 200),
            _region("r002", RegionKind.BODY, 50, 250, 500, 400),
            _region("r003", RegionKind.BODY, 50, 450, 500, 600),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002", "r003"]

    def test_furniture_excluded_from_order(self) -> None:
        regions = [
            _region("r001", RegionKind.HEADER, 0, 0, 612, 50),
            _region("r002", RegionKind.BODY, 50, 80, 500, 700),
            _region("r003", RegionKind.FOOTER, 0, 750, 612, 792),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r002"]


class TestTwoColumnLayout:
    def test_two_columns_left_to_right(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 280, 700),
            _region("r002", RegionKind.BODY, 330, 80, 560, 700),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002"]

    def test_two_columns_right_listed_first(self) -> None:
        """Order should be L-to-R regardless of input order."""
        regions = [
            _region("r002", RegionKind.BODY, 330, 80, 560, 700),
            _region("r001", RegionKind.BODY, 50, 80, 280, 700),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002"]


class TestFullWidthHeadingAboveColumns:
    def test_heading_then_two_columns(self) -> None:
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 20, 70, 590, 120),
            _region("r002", RegionKind.BODY, 50, 140, 280, 700),
            _region("r003", RegionKind.BODY, 330, 140, 560, 700),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002", "r003"]


class TestFullWidthFigureInterruptingColumns:
    def test_columns_figure_columns(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 280, 250),
            _region("r002", RegionKind.BODY, 330, 80, 560, 250),
            _region("r003", RegionKind.FIGURE_AREA, 20, 270, 590, 450),
            _region("r004", RegionKind.BODY, 50, 470, 280, 700),
            _region("r005", RegionKind.BODY, 330, 470, 560, 700),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == [
            "r001",
            "r002",
            "r003",
            "r004",
            "r005",
        ]


class TestSidebarAnchoredBesideBody:
    def test_sidebar_creates_aside_edge(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 400, 700),
            _region("r002", RegionKind.SIDEBAR, 450, 80, 560, 400),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001"]
        assert len(result.anchor_edges) == 1
        edge = result.anchor_edges[0]
        assert edge.edge_kind == AnchorEdgeKind.ASIDE_TO_MAIN
        assert edge.source_id == "r002"
        assert edge.target_id == "r001"

    def test_sidebar_not_in_main_flow(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 400, 700),
            _region("r002", RegionKind.SIDEBAR, 450, 80, 560, 400),
        ]
        result = compute_reading_order(regions)
        assert "r002" not in result.main_flow_order


class TestCalloutEmbeddedInColumns:
    def test_callout_creates_aside_edge(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 280, 700),
            _region("r002", RegionKind.CALLOUT_AREA, 330, 80, 560, 300),
            _region("r003", RegionKind.BODY, 330, 320, 560, 700),
        ]
        result = compute_reading_order(regions)
        assert "r001" in result.main_flow_order
        assert "r003" in result.main_flow_order
        assert "r002" not in result.main_flow_order
        callout_edges = [e for e in result.anchor_edges if e.source_id == "r002"]
        assert len(callout_edges) == 1
        assert callout_edges[0].edge_kind == AnchorEdgeKind.ASIDE_TO_MAIN


class TestMarginNote:
    def test_margin_note_creates_aside_edge(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 80, 80, 500, 700),
            _region("r002", RegionKind.MARGIN_NOTE, 10, 200, 70, 350),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001"]
        assert len(result.anchor_edges) == 1
        assert result.anchor_edges[0].source_id == "r002"
        assert result.anchor_edges[0].target_id == "r001"


class TestTableRegion:
    def test_table_area_in_main_flow(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 500, 300),
            _region("r002", RegionKind.TABLE_AREA, 50, 320, 500, 600),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002"]


class TestConfidence:
    def test_single_column_high_confidence(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 500, 700),
        ]
        result = compute_reading_order(regions)
        assert result.confidence == 1.0

    def test_two_column_lower_confidence(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 280, 700),
            _region("r002", RegionKind.BODY, 330, 80, 560, 700),
        ]
        result = compute_reading_order(regions)
        assert result.confidence < 1.0
        assert result.confidence >= 0.3

    def test_sidebar_reduces_confidence(self) -> None:
        body_only = [
            _region("r001", RegionKind.BODY, 50, 80, 500, 700),
        ]
        with_sidebar = [
            _region("r001", RegionKind.BODY, 50, 80, 400, 700),
            _region("r002", RegionKind.SIDEBAR, 450, 80, 560, 400),
        ]
        result_body = compute_reading_order(body_only)
        result_sidebar = compute_reading_order(with_sidebar)
        assert result_sidebar.confidence < result_body.confidence

    def test_confidence_never_below_minimum(self) -> None:
        """Even highly complex layouts should have confidence >= 0.3."""
        regions = [
            _region(f"r{i:03d}", RegionKind.BODY, 50, 80 + i * 20, 280, 95 + i * 20)
            for i in range(20)
        ]
        result = compute_reading_order(regions)
        assert result.confidence >= 0.3


class TestEdgeConfidence:
    def test_edge_confidence_uses_minimum(self) -> None:
        regions = [
            _region("r001", RegionKind.BODY, 50, 80, 400, 700, confidence=0.8),
            _region("r002", RegionKind.SIDEBAR, 450, 80, 560, 400, confidence=0.6),
        ]
        result = compute_reading_order(regions)
        assert len(result.anchor_edges) == 1
        assert result.anchor_edges[0].confidence == 0.6


class TestMixedLayout:
    def test_appendix_table_heavy_page(self) -> None:
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 20, 70, 590, 120),
            _region("r002", RegionKind.TABLE_AREA, 50, 140, 560, 400),
            _region("r003", RegionKind.TABLE_AREA, 50, 420, 560, 680),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001", "r002", "r003"]

    def test_complex_page_all_patterns(self) -> None:
        """Full-width heading, two columns, sidebar, figure interruption."""
        regions = [
            _region("r001", RegionKind.HEADER, 0, 0, 612, 50),
            _region("r002", RegionKind.FULL_WIDTH, 20, 60, 590, 100),
            _region("r003", RegionKind.BODY, 50, 110, 280, 350),
            _region("r004", RegionKind.SIDEBAR, 330, 110, 560, 250),
            _region("r005", RegionKind.BODY, 330, 260, 560, 350),
            _region("r006", RegionKind.FIGURE_AREA, 20, 370, 590, 500),
            _region("r007", RegionKind.BODY, 50, 520, 560, 700),
            _region("r008", RegionKind.FOOTER, 0, 750, 612, 792),
        ]
        result = compute_reading_order(regions)

        # Header and footer excluded
        assert "r001" not in result.main_flow_order
        assert "r008" not in result.main_flow_order

        # Sidebar excluded from main flow
        assert "r004" not in result.main_flow_order

        # Main flow order should be logical
        assert result.main_flow_order.index("r002") < result.main_flow_order.index("r003")
        assert result.main_flow_order.index("r006") < result.main_flow_order.index("r007")

        # Sidebar has an aside edge
        sidebar_edges = [e for e in result.anchor_edges if e.source_id == "r004"]
        assert len(sidebar_edges) == 1
        assert sidebar_edges[0].edge_kind == AnchorEdgeKind.ASIDE_TO_MAIN


class TestOnlyAsideRegions:
    def test_only_asides_empty_main_flow(self) -> None:
        regions = [
            _region("r001", RegionKind.SIDEBAR, 50, 80, 200, 400),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == []
        assert result.confidence == 0.5


class TestDecorativeFullWidthFilter:
    """S5U-700: FULL_WIDTH regions enclosing BODY regions are decorative.

    Red-before confirmation: at main @ 7fee026 p0042's main_flow_order
    puts r003 (FULL_WIDTH y=0-842) first because it encloses r004/r006
    BODY regions. Bottom-of-page SIDEBAR r007 (y=747) then maps aside→
    main via nearest-centre to r003 (centre y=421 is closer than r006's
    y=404 when the sidebar is deep-bottom), pulling b021 ("Crit Evade")
    to position 0. Dropping r003 leaves r006 as the sole wide main
    region and the sidebar anchors after r006's content.
    """

    def test_full_width_enclosing_body_is_dropped(self) -> None:
        """FULL_WIDTH region containing a BODY region drops from main flow."""
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 612, 792),
            _region("r002", RegionKind.BODY, 40, 60, 572, 740),
        ]
        result = compute_reading_order(regions)
        assert "r001" not in result.main_flow_order
        assert "r002" in result.main_flow_order

    def test_full_width_alone_survives(self) -> None:
        """With no BODY region, a FULL_WIDTH region stays in main flow."""
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 612, 792),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r001"]

    def test_full_width_not_enclosing_body_survives(self) -> None:
        """A FULL_WIDTH region that does NOT spatially enclose a BODY region
        (e.g., a narrower vector banner) stays in main flow.

        Adversarial: prevents over-filtering of legitimate full-bleed
        banners on pages where BODY regions extend beyond them.
        """
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 40, 60, 572, 200),
            _region("r002", RegionKind.BODY, 0, 0, 612, 792),
        ]
        result = compute_reading_order(regions)
        # r001 does NOT enclose r002 (r002 is wider and taller), so r001
        # survives.
        assert "r001" in result.main_flow_order
        assert "r002" in result.main_flow_order

    def test_sidebar_anchors_to_body_after_filter(self) -> None:
        """After filtering, a bottom-of-page SIDEBAR anchors to the BODY
        region instead of the enclosing FULL_WIDTH — fixing p0042's
        b021 ordering."""
        regions = [
            _region("r001", RegionKind.FULL_WIDTH, 0, 0, 612, 792),
            _region("r002", RegionKind.BODY, 40, 60, 572, 740),
            _region("r003", RegionKind.SIDEBAR, 300, 745, 360, 770),
        ]
        result = compute_reading_order(regions)
        assert result.main_flow_order == ["r002"]
        edges_for_sidebar = [e for e in result.anchor_edges if e.source_id == "r003"]
        assert len(edges_for_sidebar) == 1
        assert edges_for_sidebar[0].target_id == "r002"

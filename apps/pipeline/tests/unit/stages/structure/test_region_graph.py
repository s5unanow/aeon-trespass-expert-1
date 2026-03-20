"""Tests for region graph segmentation."""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.region_graph import segment_regions
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.evidence_primitives_v1 import (
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceTableCandidate,
    EvidenceVectorCluster,
)
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1

# Standard A4-like page: 612 x 792 pt
_DIMS = PageDimensions(width=612.0, height=792.0)


def _norm(rect: Rect) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / _DIMS.width)),
        y0=max(0.0, min(1.0, rect.y0 / _DIMS.height)),
        x1=max(0.0, min(1.0, rect.x1 / _DIMS.width)),
        y1=max(0.0, min(1.0, rect.y1 / _DIMS.height)),
    )


def _make_evidence(
    entities: list[object],
    dims: PageDimensions = _DIMS,
) -> PageEvidenceV1:
    return PageEvidenceV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=dims),
        entities=entities,  # type: ignore[arg-type]
    )


def _text_line(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceLine:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceLine(evidence_id=eid, text="sample", bbox=rect, norm_bbox=_norm(rect))


def _image(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceImageOccurrence:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceImageOccurrence(evidence_id=eid, bbox=rect, norm_bbox=_norm(rect))


def _table(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceTableCandidate:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceTableCandidate(evidence_id=eid, bbox=rect, norm_bbox=_norm(rect))


def _vector(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceVectorCluster:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceVectorCluster(evidence_id=eid, bbox=rect, norm_bbox=_norm(rect))


class TestEmptyEvidence:
    def test_no_entities_returns_empty(self) -> None:
        evidence = _make_evidence([])
        regions = segment_regions(evidence, StructureConfig())
        assert regions == []


class TestFurnitureZones:
    def test_header_detected(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 10, 200, 25),  # header zone
                _text_line("e.line.002", 50, 100, 500, 120),  # body
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        header = [r for r in regions if r.kind == RegionKind.HEADER]
        assert len(header) == 1
        assert header[0].evidence_ids == ["e.line.001"]

    def test_footer_detected(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),  # body
                _text_line("e.line.002", 50, 760, 200, 775),  # footer zone
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        footer = [r for r in regions if r.kind == RegionKind.FOOTER]
        assert len(footer) == 1
        assert footer[0].evidence_ids == ["e.line.002"]

    def test_header_and_footer(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 10, 200, 25),
                _text_line("e.line.002", 50, 200, 500, 220),
                _text_line("e.line.003", 50, 760, 200, 775),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        kinds = {r.kind for r in regions}
        assert RegionKind.HEADER in kinds
        assert RegionKind.FOOTER in kinds


class TestFullWidthElements:
    def test_full_width_image_creates_figure_region(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),
                _image("e.img.001", 10, 300, 600, 500),  # ~98% page width
                _text_line("e.line.002", 50, 550, 500, 570),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        figure = [r for r in regions if r.kind == RegionKind.FIGURE_AREA]
        assert len(figure) == 1
        assert figure[0].evidence_ids == ["e.img.001"]

    def test_full_width_table_creates_table_region(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),
                _table("e.tbl.001", 10, 300, 600, 500),
                _text_line("e.line.002", 50, 550, 500, 570),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        tables = [r for r in regions if r.kind == RegionKind.TABLE_AREA]
        assert len(tables) == 1


class TestSingleColumnBody:
    def test_single_column_text_is_body(self) -> None:
        lines = [
            _text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 500, 95 + i * 20) for i in range(10)
        ]
        evidence = _make_evidence(lines)
        regions = segment_regions(evidence, StructureConfig())
        body = [r for r in regions if r.kind == RegionKind.BODY]
        assert len(body) >= 1
        # All text lines should be in body regions
        body_eids = {eid for r in body for eid in r.evidence_ids}
        for line in lines:
            assert line.evidence_id in body_eids


class TestTwoColumnDetection:
    def test_two_columns_detected(self) -> None:
        # Left column (x: 50-280)
        left = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 280, 95 + i * 20) for i in range(8)]
        # Right column (x: 330-560) — gutter at 280-330 (50pt gap)
        right = [
            _text_line(f"e.line.{i + 8:03d}", 330, 80 + i * 20, 560, 95 + i * 20) for i in range(8)
        ]
        evidence = _make_evidence(left + right)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        # Should produce at least 2 body/sidebar regions
        content_regions = [
            r for r in regions if r.kind not in (RegionKind.HEADER, RegionKind.FOOTER)
        ]
        assert len(content_regions) >= 2


class TestSidebarDetection:
    def test_narrow_column_is_sidebar(self) -> None:
        # Wide left column (x: 50-400, ~57% page width)
        left = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 400, 95 + i * 20) for i in range(8)]
        # Narrow right column (x: 450-560, ~18% page width → sidebar)
        right = [
            _text_line(f"e.line.{i + 8:03d}", 450, 80 + i * 20, 560, 95 + i * 20) for i in range(4)
        ]
        evidence = _make_evidence(left + right)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        sidebar = [r for r in regions if r.kind == RegionKind.SIDEBAR]
        assert len(sidebar) >= 1


class TestRegionIds:
    def test_region_ids_are_unique(self) -> None:
        lines = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 500, 95 + i * 20) for i in range(5)]
        evidence = _make_evidence(lines)
        regions = segment_regions(evidence, StructureConfig())
        ids = [r.region_id for r in regions]
        assert len(ids) == len(set(ids))

    def test_region_id_format(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        for r in regions:
            assert r.region_id.startswith("r")
            assert len(r.region_id) == 4  # r001


class TestNormBbox:
    def test_norm_bbox_in_unit_range(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),
                _image("e.img.001", 10, 300, 600, 500),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        for r in regions:
            assert 0.0 <= r.norm_bbox.x0 <= 1.0
            assert 0.0 <= r.norm_bbox.y0 <= 1.0
            assert 0.0 <= r.norm_bbox.x1 <= 1.0
            assert 0.0 <= r.norm_bbox.y1 <= 1.0


class TestConfidence:
    def test_confidence_in_valid_range(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 100, 500, 120),
                _text_line("e.line.002", 50, 10, 200, 25),
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        for r in regions:
            assert 0.0 <= r.confidence <= 1.0


class TestEvidenceTraceability:
    def test_all_items_assigned_to_regions(self) -> None:
        lines = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 500, 95 + i * 20) for i in range(5)]
        evidence = _make_evidence(lines)
        regions = segment_regions(evidence, StructureConfig())
        all_eids = {eid for r in regions for eid in r.evidence_ids}
        for line in lines:
            assert line.evidence_id in all_eids

    def test_furniture_items_in_furniture_regions(self) -> None:
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 10, 200, 25),  # header
                _text_line("e.line.002", 50, 100, 500, 120),  # body
                _text_line("e.line.003", 50, 760, 200, 775),  # footer
            ]
        )
        regions = segment_regions(evidence, StructureConfig())
        header = next(r for r in regions if r.kind == RegionKind.HEADER)
        footer = next(r for r in regions if r.kind == RegionKind.FOOTER)
        assert "e.line.001" in header.evidence_ids
        assert "e.line.003" in footer.evidence_ids


class TestConfigOverrides:
    def test_custom_furniture_thresholds(self) -> None:
        cfg = StructureConfig(
            furniture_top_max_y=50.0,
            furniture_bottom_min_y=700.0,
        )
        evidence = _make_evidence(
            [
                _text_line("e.line.001", 50, 10, 200, 25),  # y1=25 < 50 → header
                _text_line("e.line.002", 50, 100, 500, 120),
                _text_line("e.line.003", 50, 720, 200, 735),  # y0=720 >= 700 → footer
            ]
        )
        regions = segment_regions(evidence, cfg)
        header = [r for r in regions if r.kind == RegionKind.HEADER]
        footer = [r for r in regions if r.kind == RegionKind.FOOTER]
        assert len(header) == 1
        assert len(footer) == 1

    def test_custom_gutter_width(self) -> None:
        # Two columns with 50pt gap. With default gutter (10pt), splits.
        # With very high gutter requirement (300pt), should NOT split.
        left = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 280, 95 + i * 20) for i in range(8)]
        right = [
            _text_line(f"e.line.{i + 8:03d}", 330, 80 + i * 20, 560, 95 + i * 20) for i in range(8)
        ]
        evidence = _make_evidence(left + right)

        # Default config: should split
        cfg_split = StructureConfig(gutter_min_width_pt=10.0)
        regions_split = segment_regions(evidence, cfg_split)
        content_split = [
            r for r in regions_split if r.kind not in (RegionKind.HEADER, RegionKind.FOOTER)
        ]
        assert len(content_split) >= 2

        # High gutter requirement: histogram gap (~245pt) < 300pt → no split
        cfg_no_split = StructureConfig(gutter_min_width_pt=300.0)
        regions_no = segment_regions(evidence, cfg_no_split)
        content_no = [r for r in regions_no if r.kind not in (RegionKind.HEADER, RegionKind.FOOTER)]
        assert len(content_no) == 1

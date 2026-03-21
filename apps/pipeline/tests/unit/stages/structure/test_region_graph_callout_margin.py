"""Tests for CALLOUT_AREA and MARGIN_NOTE classification in region graph."""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.region_graph import segment_regions
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.evidence_primitives_v1 import (
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceVectorCluster,
)
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1

_DIMS = PageDimensions(width=612.0, height=792.0)


def _norm(rect: Rect) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / _DIMS.width)),
        y0=max(0.0, min(1.0, rect.y0 / _DIMS.height)),
        x1=max(0.0, min(1.0, rect.x1 / _DIMS.width)),
        y1=max(0.0, min(1.0, rect.y1 / _DIMS.height)),
    )


def _make_evidence(entities: list[object], dims: PageDimensions = _DIMS) -> PageEvidenceV1:
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


def _vector(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceVectorCluster:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceVectorCluster(evidence_id=eid, bbox=rect, norm_bbox=_norm(rect))


class TestMarginNote:
    def test_narrow_left_edge_column(self) -> None:
        """Very narrow column at the left page edge → MARGIN_NOTE."""
        body = [_text_line(f"e.line.{i:03d}", 120, 80 + i * 20, 560, 95 + i * 20) for i in range(8)]
        margin = [
            _text_line(f"e.line.{i + 8:03d}", 10, 80 + i * 20, 80, 95 + i * 20) for i in range(3)
        ]
        evidence = _make_evidence(body + margin)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        mn = [r for r in regions if r.kind == RegionKind.MARGIN_NOTE]
        assert len(mn) >= 1
        mn_eids = {eid for r in mn for eid in r.evidence_ids}
        for m in margin:
            assert m.evidence_id in mn_eids

    def test_narrow_right_edge_column(self) -> None:
        """Very narrow column at the right page edge → MARGIN_NOTE."""
        body = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 480, 95 + i * 20) for i in range(8)]
        margin = [
            _text_line(f"e.line.{i + 8:03d}", 540, 80 + i * 20, 600, 95 + i * 20) for i in range(3)
        ]
        evidence = _make_evidence(body + margin)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        mn = [r for r in regions if r.kind == RegionKind.MARGIN_NOTE]
        assert len(mn) >= 1

    def test_narrow_not_at_edge_is_sidebar(self) -> None:
        """Narrow text column NOT at page edge stays SIDEBAR."""
        body = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 350, 95 + i * 20) for i in range(8)]
        # Narrow column (x: 450-560) but x0=450 is 450pt from left (>> 40pt edge margin)
        narrow = [
            _text_line(f"e.line.{i + 8:03d}", 450, 80 + i * 20, 560, 95 + i * 20) for i in range(4)
        ]
        evidence = _make_evidence(body + narrow)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        sidebar = [r for r in regions if r.kind == RegionKind.SIDEBAR]
        mn = [r for r in regions if r.kind == RegionKind.MARGIN_NOTE]
        assert len(sidebar) >= 1
        assert len(mn) == 0


class TestCalloutArea:
    def test_mixed_text_vector(self) -> None:
        """Narrow column with text + vector decoration → CALLOUT_AREA."""
        body = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 380, 95 + i * 20) for i in range(8)]
        callout = [
            _text_line("e.line.020", 420, 80, 560, 95),
            _text_line("e.line.021", 420, 100, 560, 115),
            _vector("e.vec.001", 420, 120, 560, 160),
        ]
        evidence = _make_evidence(body + callout)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        ca = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(ca) >= 1
        ca_eids = {eid for r in ca for eid in r.evidence_ids}
        assert "e.vec.001" in ca_eids

    def test_mixed_text_image(self) -> None:
        """Narrow column with text + image (text-dominated) → CALLOUT_AREA."""
        body = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 380, 95 + i * 20) for i in range(8)]
        callout = [
            _text_line("e.line.030", 420, 80, 560, 95),
            _text_line("e.line.031", 420, 100, 560, 115),
            _text_line("e.line.032", 420, 120, 560, 135),
            _image("e.img.010", 420, 140, 560, 200),
        ]
        evidence = _make_evidence(body + callout)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        ca = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(ca) >= 1

    def test_wide_mixed_not_callout(self) -> None:
        """Column wider than callout_max with mixed content → BODY, not CALLOUT."""
        # Single wide column with text + vector (width ~90% of page)
        items = [
            _text_line(f"e.line.{i:03d}", 30, 80 + i * 20, 580, 95 + i * 20) for i in range(5)
        ] + [_vector("e.vec.001", 30, 200, 580, 260)]
        evidence = _make_evidence(items)
        regions = segment_regions(evidence, StructureConfig())

        ca = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(ca) == 0


class TestEndToEndEvidenceToRegion:
    def test_callout_from_evidence(self) -> None:
        """PageEvidenceV1 → segment_regions → ResolvedRegion with CALLOUT_AREA."""
        body = [_text_line(f"e.line.{i:03d}", 50, 80 + i * 20, 380, 95 + i * 20) for i in range(8)]
        callout = [
            _text_line("e.line.050", 420, 80, 560, 95),
            _vector("e.vec.010", 420, 100, 560, 160),
        ]
        evidence = _make_evidence(body + callout)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        ca = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(ca) >= 1
        r = ca[0]
        assert r.region_id.startswith("r")
        assert 0.0 <= r.confidence <= 1.0
        assert 0.0 <= r.norm_bbox.x0 <= 1.0

    def test_margin_note_from_evidence(self) -> None:
        """PageEvidenceV1 → segment_regions → ResolvedRegion with MARGIN_NOTE."""
        body = [_text_line(f"e.line.{i:03d}", 120, 80 + i * 20, 560, 95 + i * 20) for i in range(8)]
        margin = [
            _text_line(f"e.line.{i + 8:03d}", 10, 80 + i * 20, 80, 95 + i * 20) for i in range(3)
        ]
        evidence = _make_evidence(body + margin)
        cfg = StructureConfig(gutter_min_width_pt=10.0)
        regions = segment_regions(evidence, cfg)

        mn = [r for r in regions if r.kind == RegionKind.MARGIN_NOTE]
        assert len(mn) >= 1
        r = mn[0]
        assert r.region_id.startswith("r")
        assert 0.0 <= r.confidence <= 1.0

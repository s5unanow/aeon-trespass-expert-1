"""Two-column body classification tests (S5U-700).

Covers the p0048 regression where the structure stage classified each
column as CALLOUT_AREA (because width<55% with mixed content). With
the S5U-700 fix, when a band has ≥2 body-width (>=35%) siblings that
each carry text, each is classified as BODY.

Red-before confirmation: at main @ bdb4b1b the test
``test_two_body_width_siblings_both_body`` fails because
``_classify_column`` has no sibling-aware promotion; both columns fall
through to the callout branch. See S5U-700 plan.
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.region_graph import segment_regions
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.evidence_primitives_v1 import (
    EvidenceLine,
    EvidenceVectorCluster,
)
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1

# A4 page dimensions (same as ATO source)
_DIMS = PageDimensions(width=595.0, height=842.0)


def _norm(rect: Rect) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / _DIMS.width)),
        y0=max(0.0, min(1.0, rect.y0 / _DIMS.height)),
        x1=max(0.0, min(1.0, rect.x1 / _DIMS.width)),
        y1=max(0.0, min(1.0, rect.y1 / _DIMS.height)),
    )


def _text(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceLine:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceLine(evidence_id=eid, text="sample", bbox=rect, norm_bbox=_norm(rect))


def _vector(eid: str, x0: float, y0: float, x1: float, y1: float) -> EvidenceVectorCluster:
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)
    return EvidenceVectorCluster(evidence_id=eid, bbox=rect, norm_bbox=_norm(rect))


def _make_evidence(entities: list[object]) -> PageEvidenceV1:
    return PageEvidenceV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        entities=entities,  # type: ignore[arg-type]
    )


class TestTwoBodyColumnClassification:
    def test_two_body_width_siblings_both_body(self) -> None:
        """p0048 shape: two ~250pt-wide sibling columns with interleaved text+vectors.

        Each column is ~42% of page width (< 55% callout threshold) but
        ≥35% body threshold, and both carry text → both must be BODY.
        The vectors are placed INSIDE the same vertical band as text so
        the band splitter cannot segregate them — otherwise the test
        degenerates to the single-kind case.
        """
        left: list[object] = []
        right: list[object] = []
        for i in range(6):
            left.append(_text(f"e.line.{i:03d}", 50, 100 + i * 15, 290, 112 + i * 15))
            right.append(_text(f"e.line.{i + 100:03d}", 310, 100 + i * 15, 560, 112 + i * 15))
        left.append(_vector("e.vec.001", 50, 195, 290, 220))
        right.append(_vector("e.vec.002", 310, 195, 560, 220))
        for i in range(2):
            left.append(_text(f"e.line.{i + 20:03d}", 50, 225 + i * 15, 290, 237 + i * 15))
            right.append(_text(f"e.line.{i + 120:03d}", 310, 225 + i * 15, 560, 237 + i * 15))
        evidence = _make_evidence(left + right)
        regions = segment_regions(evidence, StructureConfig(gutter_min_width_pt=10.0))

        body = [r for r in regions if r.kind == RegionKind.BODY]
        callout = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(body) >= 2, f"expected >=2 BODY; got {[(r.region_id, r.kind) for r in regions]}"
        assert len(callout) == 0, f"expected no CALLOUT; got {[r.region_id for r in callout]}"

    def test_single_narrow_mixed_callout_preserved(self) -> None:
        """A single narrow mixed text+vector column (no sibling) still CALLOUT."""
        body = [_text(f"e.line.{i:03d}", 50, 100 + i * 20, 380, 115 + i * 20) for i in range(8)]
        callout = [
            _text("e.line.100", 420, 100, 560, 115),
            _text("e.line.101", 420, 120, 560, 135),
            _vector("e.vec.001", 420, 150, 560, 200),
        ]
        evidence = _make_evidence(body + callout)  # type: ignore[arg-type]
        regions = segment_regions(evidence, StructureConfig(gutter_min_width_pt=10.0))

        ca = [r for r in regions if r.kind == RegionKind.CALLOUT_AREA]
        assert len(ca) >= 1  # Adversarial case — narrow callout preserved

    def test_narrow_sidebar_preserved_with_body_sibling(self) -> None:
        """A narrow sibling (<35% width) with a wide sibling is NOT promoted to BODY.

        The narrow sibling should keep its aside classification — SIDEBAR,
        MARGIN_NOTE, or CALLOUT_AREA depending on its exact geometry — the
        key invariant is "not silently promoted to BODY".
        """
        body = [_text(f"e.line.{i:03d}", 50, 100 + i * 20, 400, 115 + i * 20) for i in range(8)]
        narrow = [
            _text(f"e.line.{i + 8:03d}", 450, 100 + i * 20, 560, 115 + i * 20) for i in range(4)
        ]
        evidence = _make_evidence(body + narrow)
        regions = segment_regions(evidence, StructureConfig(gutter_min_width_pt=10.0))

        body_regions = [r for r in regions if r.kind == RegionKind.BODY]
        aside_regions = [
            r
            for r in regions
            if r.kind in (RegionKind.SIDEBAR, RegionKind.MARGIN_NOTE, RegionKind.CALLOUT_AREA)
        ]
        # Exactly one body region (the wide 350pt left column). The narrow
        # right column must NOT have been promoted to body by the
        # sibling-aware rule — it stays as a legitimate aside.
        assert len(body_regions) == 1
        assert len(aside_regions) >= 1

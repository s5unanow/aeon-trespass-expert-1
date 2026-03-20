"""Contract roundtrip tests for PageEvidenceV1 and ResolvedPageV1."""

import json

import pytest
from pydantic import ValidationError

from atr_schemas.common import NormRect, PageDimensions, ProvenanceRef, Rect
from atr_schemas.enums import (
    AnchorEdgeKind,
    BlockType,
    RegionKind,
    SymbolAnchorKind,
)
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceRegionCandidate,
    EvidenceTableCandidate,
    EvidenceTextSpan,
    EvidenceVectorCluster,
    EvidenceVectorPath,
)
from atr_schemas.page_evidence_v1 import (
    EvidenceTransformMeta,
    PageEvidenceV1,
)
from atr_schemas.resolved_page_v1 import (
    AnchorEdge,
    FallbackProvenance,
    ResolvedBlock,
    ResolvedPageV1,
    ResolvedRegion,
    ResolvedSymbolRef,
    SemanticConfidence,
)

_RECT = Rect(x0=50.0, y0=100.0, x1=200.0, y1=120.0)
_NORM = NormRect(x0=0.08, y0=0.12, x1=0.34, y1=0.14)
_DIMS = PageDimensions(width=595.2, height=841.8)


def _roundtrip(model_instance: object) -> None:
    model_cls = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
    assert restored == model_instance


# --- PageEvidenceV1 roundtrip ---


def test_page_evidence_roundtrip() -> None:
    evidence = PageEvidenceV1(
        document_id="ato_core_v1_1",
        page_id="p0042",
        page_number=42,
        transform=EvidenceTransformMeta(
            source_native_hash="abc123",
            extractor="pymupdf",
            extractor_version="1.25.0",
            page_dimensions_pt=_DIMS,
        ),
        entities=[
            EvidenceChar(
                evidence_id="e.char.001",
                text="A",
                bbox=_RECT,
                norm_bbox=_NORM,
                font_name="Arial",
                font_size=12.0,
            ),
            EvidenceLine(
                evidence_id="e.line.001",
                text="Attack Test",
                bbox=_RECT,
                norm_bbox=_NORM,
                char_ids=["e.char.001"],
            ),
            EvidenceTextSpan(
                evidence_id="e.span.001",
                text="Attack",
                bbox=_RECT,
                norm_bbox=_NORM,
                font_name="Arial",
                font_size=12.0,
            ),
            EvidenceImageOccurrence(
                evidence_id="e.img.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                width_px=14,
                height_px=14,
                image_hash="deadbeef",
            ),
            EvidenceVectorPath(
                evidence_id="e.vec.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                path_ops=["m", "l", "c"],
            ),
            EvidenceVectorCluster(
                evidence_id="e.vclust.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                path_ids=["e.vec.001"],
                cluster_hash="cafebabe",
            ),
            EvidenceTableCandidate(
                evidence_id="e.tbl.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                row_count=3,
                col_count=2,
                confidence=0.85,
            ),
            EvidenceRegionCandidate(
                evidence_id="e.reg.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                region_kind=RegionKind.BODY,
                confidence=0.92,
            ),
        ],
    )
    _roundtrip(evidence)


def test_evidence_discriminated_union_from_dicts() -> None:
    raw: dict[str, object] = {
        "schema_version": "page_evidence.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "transform": {
            "page_dimensions_pt": {"width": 595.2, "height": 841.8},
        },
        "entities": [
            {
                "kind": "char",
                "evidence_id": "e.char.001",
                "text": "X",
                "bbox": {"x0": 10, "y0": 20, "x1": 15, "y1": 30},
                "norm_bbox": {"x0": 0.02, "y0": 0.02, "x1": 0.03, "y1": 0.04},
            },
            {
                "kind": "image_occurrence",
                "evidence_id": "e.img.001",
                "bbox": {"x0": 100, "y0": 100, "x1": 200, "y1": 200},
                "norm_bbox": {"x0": 0.17, "y0": 0.12, "x1": 0.34, "y1": 0.24},
            },
            {
                "kind": "region_candidate",
                "evidence_id": "e.reg.001",
                "bbox": {"x0": 50, "y0": 50, "x1": 545, "y1": 790},
                "norm_bbox": {"x0": 0.08, "y0": 0.06, "x1": 0.92, "y1": 0.94},
                "region_kind": "sidebar",
            },
        ],
    }
    page = PageEvidenceV1.model_validate(raw)
    assert len(page.entities) == 3
    assert isinstance(page.entities[0], EvidenceChar)
    assert isinstance(page.entities[1], EvidenceImageOccurrence)
    assert isinstance(page.entities[2], EvidenceRegionCandidate)
    assert page.entities[2].region_kind == RegionKind.SIDEBAR


def test_page_evidence_empty_entities() -> None:
    evidence = PageEvidenceV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
    )
    _roundtrip(evidence)
    assert evidence.entities == []


# --- ResolvedPageV1 roundtrip ---


def test_resolved_page_roundtrip() -> None:
    resolved = ResolvedPageV1(
        document_id="ato_core_v1_1",
        page_id="p0042",
        page_number=42,
        source_evidence_hash="abc123",
        regions=[
            ResolvedRegion(
                region_id="r001",
                kind=RegionKind.BODY,
                bbox=_RECT,
                norm_bbox=_NORM,
                evidence_ids=["e.reg.001"],
                confidence=0.95,
            ),
        ],
        blocks=[
            ResolvedBlock(
                block_id="p0042.b001",
                block_type=BlockType.HEADING,
                region_id="r001",
                evidence_ids=["e.span.001", "e.span.002"],
                confidence=0.98,
            ),
            ResolvedBlock(
                block_id="p0042.b002",
                block_type=BlockType.PARAGRAPH,
                region_id="r001",
                evidence_ids=["e.span.003"],
                symbol_refs=[
                    ResolvedSymbolRef(
                        symbol_id="sym.progress",
                        instance_id="syminst.p0042.01",
                        anchor_kind=SymbolAnchorKind.INLINE,
                        evidence_ids=["e.img.001"],
                        confidence=0.93,
                    ),
                ],
                fallback=FallbackProvenance(
                    strategy="primary",
                ),
            ),
        ],
        main_flow_order=["p0042.b001", "p0042.b002"],
        anchor_edges=[
            AnchorEdge(
                edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
                source_id="p0042.b001",
                target_id="r001",
            ),
        ],
        symbol_refs=[
            ResolvedSymbolRef(
                symbol_id="sym.progress",
                anchor_kind=SymbolAnchorKind.INLINE,
                evidence_ids=["e.img.001"],
            ),
        ],
        confidence=SemanticConfidence(
            overall=0.94,
            region_segmentation=0.95,
            reading_order=0.98,
            block_classification=0.92,
            symbol_resolution=0.93,
        ),
        provenance=ProvenanceRef(extractor="structure_v3", version="1"),
    )
    _roundtrip(resolved)


def test_resolved_page_from_dicts() -> None:
    raw: dict[str, object] = {
        "schema_version": "resolved_page.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "regions": [
            {
                "region_id": "r001",
                "kind": "body",
                "bbox": {"x0": 50, "y0": 50, "x1": 545, "y1": 790},
                "norm_bbox": {"x0": 0.08, "y0": 0.06, "x1": 0.92, "y1": 0.94},
            },
        ],
        "blocks": [
            {
                "block_id": "p0001.b001",
                "block_type": "heading",
                "region_id": "r001",
            },
        ],
        "main_flow_order": ["p0001.b001"],
    }
    page = ResolvedPageV1.model_validate(raw)
    assert len(page.regions) == 1
    assert page.regions[0].kind == RegionKind.BODY
    assert page.blocks[0].block_type == BlockType.HEADING


# --- Validation tests (negative) ---


def test_norm_rect_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        NormRect(x0=-0.1, y0=0.0, x1=0.5, y1=0.5)
    with pytest.raises(ValidationError):
        NormRect(x0=0.0, y0=0.0, x1=1.1, y1=0.5)


def test_page_evidence_rejects_bad_page_id() -> None:
    with pytest.raises(ValidationError):
        PageEvidenceV1(
            document_id="test",
            page_id="bad",
            page_number=1,
            transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        )


def test_resolved_page_rejects_bad_schema_version() -> None:
    with pytest.raises(ValidationError):
        ResolvedPageV1.model_validate(
            {
                "schema_version": "wrong.v1",
                "document_id": "test",
                "page_id": "p0001",
                "page_number": 1,
            }
        )


def test_confidence_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SemanticConfidence(overall=1.5)


def test_evidence_id_pattern_validation() -> None:
    """Valid evidence IDs are accepted, invalid ones rejected."""
    char = EvidenceChar(
        evidence_id="e.char.001",
        text="A",
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    assert char.evidence_id == "e.char.001"

    with pytest.raises(ValidationError):
        EvidenceChar(
            evidence_id="bad_id",
            text="A",
            bbox=_RECT,
            norm_bbox=_NORM,
        )


def test_region_id_pattern_validation() -> None:
    """Valid region IDs are accepted, invalid ones rejected."""
    region = ResolvedRegion(
        region_id="r001",
        kind=RegionKind.BODY,
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    assert region.region_id == "r001"

    with pytest.raises(ValidationError):
        ResolvedRegion(
            region_id="bad",
            kind=RegionKind.BODY,
            bbox=_RECT,
            norm_bbox=_NORM,
        )

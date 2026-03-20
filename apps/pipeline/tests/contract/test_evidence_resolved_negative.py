"""Negative-fixture validation for PageEvidenceV1 and ResolvedPageV1.

Tests that invalid inputs are rejected with explicit validation errors.
Complements the roundtrip tests in test_evidence_resolved_roundtrip.py.
"""

import pytest
from pydantic import ValidationError

from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import AnchorEdgeKind, BlockType, RegionKind, SymbolAnchorKind
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
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
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
_TRANSFORM = EvidenceTransformMeta(page_dimensions_pt=_DIMS)
_EVIDENCE_RAW = {
    "document_id": "test",
    "page_id": "p0001",
    "page_number": 1,
    "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
}
_RESOLVED_RAW = {"document_id": "test", "page_id": "p0001", "page_number": 1}


# --- Evidence ID pattern ---

_BAD_EVIDENCE_IDS = ["bad_id", "e.char", "e.char.", "char.001", "e..001", "e.char.01", ""]


@pytest.mark.parametrize("bad_id", [*_BAD_EVIDENCE_IDS, "E.CHAR.001"])
def test_evidence_char_rejects_bad_evidence_id(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="evidence_id"):
        EvidenceChar(evidence_id=bad_id, text="A", bbox=_RECT, norm_bbox=_NORM)


@pytest.mark.parametrize(
    "entity_cls,kind",
    [
        (EvidenceLine, "line"),
        (EvidenceTextSpan, "text_span"),
        (EvidenceImageOccurrence, "image_occurrence"),
        (EvidenceVectorPath, "vector_path"),
        (EvidenceVectorCluster, "vector_cluster"),
        (EvidenceTableCandidate, "table_candidate"),
        (EvidenceRegionCandidate, "region_candidate"),
    ],
)
def test_all_entity_types_reject_bad_evidence_id(entity_cls: type, kind: str) -> None:
    base: dict[str, object] = {"evidence_id": "nope", "bbox": _RECT, "norm_bbox": _NORM}
    if kind in ("line", "text_span"):
        base["text"] = "x"
    with pytest.raises(ValidationError, match="evidence_id"):
        entity_cls(**base)


# --- NormRect bounds ---


@pytest.mark.parametrize(
    "field,value",
    [("x0", -0.01), ("y0", -0.5), ("x1", 1.01), ("y1", 2.0)],
)
def test_norm_rect_rejects_each_bound(field: str, value: float) -> None:
    kwargs = {"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.5, field: value}
    with pytest.raises(ValidationError):
        NormRect(**kwargs)


# --- Confidence bounds (all entities and models with confidence) ---


@pytest.mark.parametrize("bad_val", [-0.1, 1.1, 2.0, -1.0])
def test_table_candidate_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        EvidenceTableCandidate(
            evidence_id="e.tbl.001", bbox=_RECT, norm_bbox=_NORM, confidence=bad_val
        )


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_region_candidate_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        EvidenceRegionCandidate(
            evidence_id="e.reg.001", bbox=_RECT, norm_bbox=_NORM, confidence=bad_val
        )


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_resolved_region_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        ResolvedRegion(
            region_id="r001",
            kind=RegionKind.BODY,
            bbox=_RECT,
            norm_bbox=_NORM,
            confidence=bad_val,
        )


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_resolved_block_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        ResolvedBlock(block_id="p0001.b001", block_type=BlockType.PARAGRAPH, confidence=bad_val)


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_symbol_ref_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        ResolvedSymbolRef(
            symbol_id="sym.x", anchor_kind=SymbolAnchorKind.INLINE, confidence=bad_val
        )


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_anchor_edge_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        AnchorEdge(
            edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
            source_id="b001",
            target_id="r001",
            confidence=bad_val,
        )


@pytest.mark.parametrize("bad_val", [-0.1, 1.5])
def test_fallback_provenance_rejects_bad_confidence(bad_val: float) -> None:
    with pytest.raises(ValidationError, match="original_confidence"):
        FallbackProvenance(strategy="primary", original_confidence=bad_val)


@pytest.mark.parametrize(
    "field",
    [
        "overall",
        "region_segmentation",
        "reading_order",
        "block_classification",
        "symbol_resolution",
    ],
)
def test_semantic_confidence_rejects_each_field_out_of_range(field: str) -> None:
    with pytest.raises(ValidationError):
        SemanticConfidence(**{field: 1.5})
    with pytest.raises(ValidationError):
        SemanticConfidence(**{field: -0.1})


# --- Page ID / Region ID / Schema version patterns ---


@pytest.mark.parametrize("bad_id", ["p1", "p12345", "page1", "0001", ""])
def test_page_evidence_rejects_various_bad_page_ids(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="page_id"):
        PageEvidenceV1(document_id="test", page_id=bad_id, page_number=1, transform=_TRANSFORM)


@pytest.mark.parametrize("bad_id", ["p1", "p12345", "page1", "0001", ""])
def test_resolved_page_rejects_various_bad_page_ids(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="page_id"):
        ResolvedPageV1(document_id="test", page_id=bad_id, page_number=1)


@pytest.mark.parametrize("bad_id", ["r01", "r0001", "region1", "001", ""])
def test_region_id_rejects_bad_patterns(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="region_id"):
        ResolvedRegion(region_id=bad_id, kind=RegionKind.BODY, bbox=_RECT, norm_bbox=_NORM)


@pytest.mark.parametrize(
    "bad_version",
    ["wrong.v1", "page_evidence.v", "page_evidence.1", "resolved_page.v1", ""],
)
def test_evidence_rejects_bad_schema_version(bad_version: str) -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        PageEvidenceV1.model_validate({**_EVIDENCE_RAW, "schema_version": bad_version})


@pytest.mark.parametrize(
    "bad_version",
    ["wrong.v1", "resolved_page.v", "resolved_page.1", "page_evidence.v1", ""],
)
def test_resolved_rejects_bad_schema_version(bad_version: str) -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        ResolvedPageV1.model_validate({**_RESOLVED_RAW, "schema_version": bad_version})


# --- Invalid enum values via raw dicts ---


def test_evidence_rejects_invalid_region_kind() -> None:
    entity = {
        "kind": "region_candidate",
        "evidence_id": "e.reg.001",
        "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
        "norm_bbox": {"x0": 0, "y0": 0, "x1": 0.5, "y1": 0.5},
        "region_kind": "not_a_real_kind",
    }
    with pytest.raises(ValidationError):
        PageEvidenceV1.model_validate({**_EVIDENCE_RAW, "entities": [entity]})


def test_resolved_rejects_invalid_block_type() -> None:
    with pytest.raises(ValidationError):
        ResolvedPageV1.model_validate(
            {**_RESOLVED_RAW, "blocks": [{"block_id": "b001", "block_type": "invalid"}]}
        )


def test_resolved_rejects_invalid_anchor_kind() -> None:
    with pytest.raises(ValidationError):
        ResolvedSymbolRef.model_validate({"symbol_id": "sym.x", "anchor_kind": "not_a_real_anchor"})


def test_resolved_rejects_invalid_edge_kind() -> None:
    with pytest.raises(ValidationError):
        AnchorEdge.model_validate(
            {"edge_kind": "not_a_real_edge", "source_id": "b001", "target_id": "r001"}
        )


# --- Unknown / missing discriminator kind ---


def test_evidence_rejects_unknown_entity_kind() -> None:
    entity = {
        "kind": "unknown_kind",
        "evidence_id": "e.unk.001",
        "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
        "norm_bbox": {"x0": 0, "y0": 0, "x1": 0.5, "y1": 0.5},
    }
    with pytest.raises(ValidationError):
        PageEvidenceV1.model_validate({**_EVIDENCE_RAW, "entities": [entity]})


def test_evidence_rejects_entity_missing_kind() -> None:
    entity = {
        "evidence_id": "e.char.001",
        "text": "A",
        "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        "norm_bbox": {"x0": 0, "y0": 0, "x1": 0.1, "y1": 0.1},
    }
    with pytest.raises(ValidationError):
        PageEvidenceV1.model_validate({**_EVIDENCE_RAW, "entities": [entity]})


# --- Missing required fields ---


def test_evidence_rejects_missing_document_id() -> None:
    with pytest.raises(ValidationError, match="document_id"):
        PageEvidenceV1.model_validate(
            {"page_id": "p0001", "page_number": 1, "transform": _EVIDENCE_RAW["transform"]}
        )


def test_evidence_rejects_missing_transform() -> None:
    with pytest.raises(ValidationError, match="transform"):
        PageEvidenceV1.model_validate({"document_id": "test", "page_id": "p0001", "page_number": 1})


def test_transform_rejects_missing_dimensions() -> None:
    with pytest.raises(ValidationError, match="page_dimensions_pt"):
        EvidenceTransformMeta.model_validate({})


def test_resolved_rejects_missing_document_id() -> None:
    with pytest.raises(ValidationError, match="document_id"):
        ResolvedPageV1.model_validate({"page_id": "p0001", "page_number": 1})


def test_resolved_block_rejects_missing_block_type() -> None:
    with pytest.raises(ValidationError, match="block_type"):
        ResolvedBlock.model_validate({"block_id": "p0001.b001"})


def test_resolved_region_rejects_missing_kind() -> None:
    with pytest.raises(ValidationError, match="kind"):
        ResolvedRegion.model_validate(
            {
                "region_id": "r001",
                "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                "norm_bbox": {"x0": 0, "y0": 0, "x1": 0.5, "y1": 0.5},
            }
        )


# --- Page number constraints ---


@pytest.mark.parametrize("bad_num", [0, -1, -100])
def test_evidence_rejects_non_positive_page_number(bad_num: int) -> None:
    with pytest.raises(ValidationError, match="page_number"):
        PageEvidenceV1(
            document_id="test", page_id="p0001", page_number=bad_num, transform=_TRANSFORM
        )


@pytest.mark.parametrize("bad_num", [0, -1, -100])
def test_resolved_rejects_non_positive_page_number(bad_num: int) -> None:
    with pytest.raises(ValidationError, match="page_number"):
        ResolvedPageV1(document_id="test", page_id="p0001", page_number=bad_num)


# --- Malformed nested structures ---


def test_evidence_char_rejects_missing_text() -> None:
    with pytest.raises(ValidationError, match="text"):
        EvidenceChar.model_validate(
            {
                "evidence_id": "e.char.001",
                "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                "norm_bbox": {"x0": 0, "y0": 0, "x1": 0.1, "y1": 0.1},
            }
        )


def test_evidence_rejects_malformed_bbox() -> None:
    with pytest.raises(ValidationError):
        EvidenceChar(
            evidence_id="e.char.001",
            text="A",
            bbox={"x0": 0},  # type: ignore[arg-type]
            norm_bbox=_NORM,
        )


def test_evidence_rejects_malformed_norm_bbox() -> None:
    with pytest.raises(ValidationError):
        EvidenceChar(
            evidence_id="e.char.001",
            text="A",
            bbox=_RECT,
            norm_bbox={"x0": 0},  # type: ignore[arg-type]
        )

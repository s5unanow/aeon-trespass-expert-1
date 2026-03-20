"""JSON Schema validation and codegen freshness tests for evidence/resolved schemas.

Validates that:
1. Valid Pydantic instances pass JSON Schema validation
2. Invalid JSON payloads fail JSON Schema validation
3. Generated JSON Schema files match current Pydantic models (codegen freshness)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind, SymbolAnchorKind
from atr_schemas.evidence_primitives_v1 import (
    EvidenceChar,
    EvidenceImageOccurrence,
    EvidenceRegionCandidate,
)
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1
from atr_schemas.resolved_page_v1 import (
    ResolvedBlock,
    ResolvedPageV1,
    ResolvedRegion,
    ResolvedSymbolRef,
    SemanticConfidence,
)

_SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "packages" / "schemas" / "jsonschema"
_RECT = Rect(x0=50.0, y0=100.0, x1=200.0, y1=120.0)
_NORM = NormRect(x0=0.08, y0=0.12, x1=0.34, y1=0.14)
_DIMS = PageDimensions(width=595.2, height=841.8)


def _load_json_schema(name: str) -> dict[str, Any]:
    path = _SCHEMAS_DIR / f"{name}.schema.json"
    result: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return result


def _to_json_dict(model: object) -> dict[str, Any]:
    """Serialize a Pydantic model to a plain dict via JSON."""
    cls = type(model)
    json_str: str = cls.model_validate(model).model_dump_json()  # type: ignore[attr-defined]
    result: dict[str, Any] = json.loads(json_str)
    return result


@pytest.fixture(scope="module")
def evidence_schema() -> dict[str, Any]:
    return _load_json_schema("page_evidence_v1")


@pytest.fixture(scope="module")
def resolved_schema() -> dict[str, Any]:
    return _load_json_schema("resolved_page_v1")


# ---------------------------------------------------------------------------
# Positive validation: valid Pydantic models pass JSON Schema
# ---------------------------------------------------------------------------


def test_valid_evidence_passes_json_schema(evidence_schema: dict[str, Any]) -> None:
    evidence = PageEvidenceV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
        entities=[
            EvidenceChar(evidence_id="e.char.001", text="A", bbox=_RECT, norm_bbox=_NORM),
            EvidenceImageOccurrence(
                evidence_id="e.img.001", bbox=_RECT, norm_bbox=_NORM, image_hash="abc"
            ),
            EvidenceRegionCandidate(
                evidence_id="e.reg.001",
                bbox=_RECT,
                norm_bbox=_NORM,
                region_kind=RegionKind.BODY,
            ),
        ],
    )
    jsonschema.validate(_to_json_dict(evidence), evidence_schema)


def test_valid_evidence_empty_entities_passes(evidence_schema: dict[str, Any]) -> None:
    evidence = PageEvidenceV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        transform=EvidenceTransformMeta(page_dimensions_pt=_DIMS),
    )
    jsonschema.validate(_to_json_dict(evidence), evidence_schema)


def test_valid_resolved_passes_json_schema(resolved_schema: dict[str, Any]) -> None:
    from atr_schemas.enums import BlockType

    resolved = ResolvedPageV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        regions=[
            ResolvedRegion(region_id="r001", kind=RegionKind.BODY, bbox=_RECT, norm_bbox=_NORM),
        ],
        blocks=[
            ResolvedBlock(
                block_id="p0001.b001",
                block_type=BlockType.HEADING,
                region_id="r001",
            ),
        ],
        main_flow_order=["p0001.b001"],
        symbol_refs=[
            ResolvedSymbolRef(symbol_id="sym.x", anchor_kind=SymbolAnchorKind.INLINE),
        ],
        confidence=SemanticConfidence(overall=0.95),
    )
    jsonschema.validate(_to_json_dict(resolved), resolved_schema)


def test_valid_resolved_minimal_passes(resolved_schema: dict[str, Any]) -> None:
    resolved = ResolvedPageV1(document_id="test", page_id="p0001", page_number=1)
    jsonschema.validate(_to_json_dict(resolved), resolved_schema)


# ---------------------------------------------------------------------------
# Negative validation: invalid JSON fails JSON Schema
# ---------------------------------------------------------------------------


def test_jsonschema_rejects_missing_document_id(evidence_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "page_evidence.v1",
        "page_id": "p0001",
        "page_number": 1,
        "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
        "entities": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, evidence_schema)


def test_jsonschema_rejects_bad_page_id(evidence_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "page_evidence.v1",
        "document_id": "test",
        "page_id": "bad",
        "page_number": 1,
        "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
        "entities": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, evidence_schema)


def test_jsonschema_rejects_bad_schema_version(evidence_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "wrong.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
        "entities": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, evidence_schema)


def test_jsonschema_rejects_bad_page_number(evidence_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "page_evidence.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 0,
        "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
        "entities": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, evidence_schema)


def test_jsonschema_rejects_norm_rect_out_of_range(evidence_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "page_evidence.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "transform": {"page_dimensions_pt": {"width": 595.2, "height": 841.8}},
        "entities": [
            {
                "kind": "char",
                "evidence_id": "e.char.001",
                "text": "A",
                "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                "norm_bbox": {"x0": -0.1, "y0": 0, "x1": 0.5, "y1": 0.5},
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, evidence_schema)


def test_jsonschema_rejects_resolved_bad_page_id(resolved_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "resolved_page.v1",
        "document_id": "test",
        "page_id": "bad",
        "page_number": 1,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, resolved_schema)


def test_jsonschema_rejects_resolved_missing_document_id(
    resolved_schema: dict[str, Any],
) -> None:
    bad = {
        "schema_version": "resolved_page.v1",
        "page_id": "p0001",
        "page_number": 1,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, resolved_schema)


def test_jsonschema_rejects_confidence_over_one(resolved_schema: dict[str, Any]) -> None:
    bad = {
        "schema_version": "resolved_page.v1",
        "document_id": "test",
        "page_id": "p0001",
        "page_number": 1,
        "confidence": {"overall": 1.5},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, resolved_schema)


# ---------------------------------------------------------------------------
# Codegen freshness: generated JSON Schema matches Pydantic models
# ---------------------------------------------------------------------------


def test_evidence_jsonschema_matches_pydantic() -> None:
    """Generated JSON Schema for PageEvidenceV1 is up to date."""
    from_pydantic = PageEvidenceV1.model_json_schema()
    from_file = _load_json_schema("page_evidence_v1")
    assert from_pydantic == from_file, (
        "page_evidence_v1.schema.json is stale — run `make codegen` to regenerate"
    )


def test_resolved_jsonschema_matches_pydantic() -> None:
    """Generated JSON Schema for ResolvedPageV1 is up to date."""
    from_pydantic = ResolvedPageV1.model_json_schema()
    from_file = _load_json_schema("resolved_page_v1")
    assert from_pydantic == from_file, (
        "resolved_page_v1.schema.json is stale — run `make codegen` to regenerate"
    )

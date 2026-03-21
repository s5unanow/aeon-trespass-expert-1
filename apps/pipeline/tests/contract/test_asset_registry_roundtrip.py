"""Contract roundtrip tests for AssetClassV1, AssetOccurrenceV1, AssetRegistryV1."""

import json

from atr_schemas.asset_class_v1 import AssetClassV1, AssetIdentity
from atr_schemas.asset_occurrence_v1 import AssetOccurrenceV1
from atr_schemas.asset_registry_v1 import AssetRegistryV1
from atr_schemas.common import NormRect, Rect
from atr_schemas.enums import AssetSourceKind, OccurrenceContext

_RECT = Rect(x0=50.0, y0=100.0, x1=200.0, y1=120.0)
_NORM = NormRect(x0=0.08, y0=0.12, x1=0.34, y1=0.14)


def _roundtrip(model_instance: object) -> None:
    model_cls = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
    assert restored == model_instance


def test_asset_class_roundtrip() -> None:
    cls = AssetClassV1(
        class_id="ac.raster.deadbeef1234",
        source_kind=AssetSourceKind.EMBEDDED_RASTER,
        identity=AssetIdentity(
            exact_hash="deadbeef1234",
            fuzzy_hash="ab12cd34ef56",
        ),
        width_px=14,
        height_px=14,
        label="progress_icon",
        canonical_evidence_id="e.img.001",
    )
    _roundtrip(cls)


def test_asset_class_vector_roundtrip() -> None:
    cls = AssetClassV1(
        class_id="ac.vector.cafebabe5678",
        source_kind=AssetSourceKind.VECTOR_CLUSTER,
        identity=AssetIdentity(
            exact_hash="cafebabe5678",
            vector_signature="cafebabe5678",
        ),
        canonical_evidence_id="e.vclust.001",
    )
    _roundtrip(cls)


def test_asset_class_minimal() -> None:
    cls = AssetClassV1(
        class_id="ac.crop.000000000000",
        source_kind=AssetSourceKind.RENDERED_CROP,
    )
    _roundtrip(cls)


def test_asset_occurrence_roundtrip() -> None:
    occ = AssetOccurrenceV1(
        occurrence_id="ao.p0042.001",
        class_id="ac.raster.deadbeef1234",
        page_id="p0042",
        bbox=_RECT,
        norm_bbox=_NORM,
        context=OccurrenceContext.INLINE,
        evidence_ids=["e.img.001"],
        confidence=0.95,
    )
    _roundtrip(occ)


def test_asset_occurrence_defaults() -> None:
    occ = AssetOccurrenceV1(
        occurrence_id="ao.p0001.000",
        class_id="ac.vector.aabbccdd1234",
        page_id="p0001",
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    assert occ.context == OccurrenceContext.INLINE
    assert occ.confidence == 1.0
    assert occ.evidence_ids == []
    _roundtrip(occ)


def test_asset_registry_roundtrip() -> None:
    cls1 = AssetClassV1(
        class_id="ac.raster.deadbeef1234",
        source_kind=AssetSourceKind.EMBEDDED_RASTER,
        identity=AssetIdentity(exact_hash="deadbeef1234"),
        width_px=14,
        height_px=14,
        canonical_evidence_id="e.img.001",
    )
    cls2 = AssetClassV1(
        class_id="ac.vector.cafebabe5678",
        source_kind=AssetSourceKind.VECTOR_CLUSTER,
        identity=AssetIdentity(exact_hash="cafebabe5678"),
        canonical_evidence_id="e.vclust.001",
    )
    occ1 = AssetOccurrenceV1(
        occurrence_id="ao.p0042.000",
        class_id="ac.raster.deadbeef1234",
        page_id="p0042",
        bbox=_RECT,
        norm_bbox=_NORM,
        context=OccurrenceContext.INLINE,
        evidence_ids=["e.img.001"],
    )
    occ2 = AssetOccurrenceV1(
        occurrence_id="ao.p0043.000",
        class_id="ac.raster.deadbeef1234",
        page_id="p0043",
        bbox=_RECT,
        norm_bbox=_NORM,
        context=OccurrenceContext.REGION_FLOAT,
        evidence_ids=["e.img.003"],
    )
    registry = AssetRegistryV1(
        document_id="ato_core_v1_1",
        classes=[cls1, cls2],
        occurrences=[occ1, occ2],
    )
    _roundtrip(registry)


def test_asset_registry_empty() -> None:
    registry = AssetRegistryV1(document_id="test")
    _roundtrip(registry)
    assert registry.classes == []
    assert registry.occurrences == []


def test_registry_from_dicts() -> None:
    raw: dict[str, object] = {
        "schema_version": "asset_registry.v1",
        "document_id": "test",
        "classes": [
            {
                "class_id": "ac.raster.aabb00112233",
                "source_kind": "embedded_raster",
                "identity": {"exact_hash": "aabb00112233"},
            },
        ],
        "occurrences": [
            {
                "occurrence_id": "ao.p0001.000",
                "class_id": "ac.raster.aabb00112233",
                "page_id": "p0001",
                "bbox": {"x0": 10, "y0": 20, "x1": 30, "y1": 40},
                "norm_bbox": {"x0": 0.02, "y0": 0.02, "x1": 0.05, "y1": 0.05},
                "context": "inline",
            },
        ],
    }
    reg = AssetRegistryV1.model_validate(raw)
    assert len(reg.classes) == 1
    assert reg.classes[0].source_kind == AssetSourceKind.EMBEDDED_RASTER
    assert len(reg.occurrences) == 1
    assert reg.occurrences[0].context == OccurrenceContext.INLINE


def test_registry_lookup_helpers() -> None:
    cls = AssetClassV1(
        class_id="ac.raster.aabb",
        source_kind=AssetSourceKind.EMBEDDED_RASTER,
    )
    occ1 = AssetOccurrenceV1(
        occurrence_id="ao.p0001.000",
        class_id="ac.raster.aabb",
        page_id="p0001",
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    occ2 = AssetOccurrenceV1(
        occurrence_id="ao.p0002.000",
        class_id="ac.raster.aabb",
        page_id="p0002",
        bbox=_RECT,
        norm_bbox=_NORM,
    )
    reg = AssetRegistryV1(
        document_id="test",
        classes=[cls],
        occurrences=[occ1, occ2],
    )
    assert reg.get_class("ac.raster.aabb") == cls
    assert reg.get_class("nonexistent") is None
    assert reg.get_occurrences_for_class("ac.raster.aabb") == [occ1, occ2]
    assert reg.get_occurrences_for_page("p0001") == [occ1]
    assert reg.get_occurrences_for_page("p9999") == []

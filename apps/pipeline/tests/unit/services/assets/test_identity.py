"""Unit tests for asset identity helpers."""

from atr_pipeline.services.assets.identity import asset_class_id, occurrence_id
from atr_schemas.enums import AssetSourceKind


def test_asset_class_id_raster() -> None:
    cid = asset_class_id(AssetSourceKind.EMBEDDED_RASTER, "deadbeef12345678")
    assert cid == "ac.raster.deadbeef1234"


def test_asset_class_id_vector() -> None:
    cid = asset_class_id(AssetSourceKind.VECTOR_CLUSTER, "cafebabe56789abc")
    assert cid == "ac.vector.cafebabe5678"


def test_asset_class_id_crop() -> None:
    cid = asset_class_id(AssetSourceKind.RENDERED_CROP, "aabb00112233")
    assert cid == "ac.crop.aabb00112233"


def test_asset_class_id_empty_hash() -> None:
    cid = asset_class_id(AssetSourceKind.EMBEDDED_RASTER, "")
    assert cid == "ac.raster.000000000000"


def test_asset_class_id_short_hash() -> None:
    cid = asset_class_id(AssetSourceKind.EMBEDDED_RASTER, "abc")
    assert cid == "ac.raster.abc"


def test_occurrence_id_format() -> None:
    oid = occurrence_id("p0042", 0)
    assert oid == "ao.p0042.000"


def test_occurrence_id_multi_digit() -> None:
    oid = occurrence_id("p0001", 15)
    assert oid == "ao.p0001.015"

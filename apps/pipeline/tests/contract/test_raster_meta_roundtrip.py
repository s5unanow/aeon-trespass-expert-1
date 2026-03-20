"""Contract roundtrip tests for RasterMetaV1."""

import json
from typing import Any

from pydantic import BaseModel

from atr_schemas.raster_meta_v1 import RasterLevel, RasterMetaV1


def _roundtrip(model_instance: BaseModel) -> None:
    """Serialize to JSON and deserialize back, assert equality."""
    model_cls: type[Any] = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
    assert restored == model_instance


def test_raster_level_roundtrip() -> None:
    level = RasterLevel(
        dpi=300,
        width_px=2480,
        height_px=3508,
        content_hash="abc123def456",
        relative_path="test_doc/raster/page/p0001__300dpi/abc123def456.png",
    )
    _roundtrip(level)


def test_raster_meta_roundtrip() -> None:
    meta = RasterMetaV1(
        document_id="ato_core_v1_1",
        page_id="p0001",
        page_number=1,
        source_pdf_sha256="abcdef123456",
        render_engine="pymupdf",
        render_engine_version="1.24.0",
        levels=[
            RasterLevel(
                dpi=150,
                width_px=1240,
                height_px=1754,
                content_hash="aaa111bbb222",
                relative_path="ato_core_v1_1/raster/page/p0001__150dpi/aaa111bbb222.png",
            ),
            RasterLevel(
                dpi=300,
                width_px=2480,
                height_px=3508,
                content_hash="ccc333ddd444",
                relative_path="ato_core_v1_1/raster/page/p0001__300dpi/ccc333ddd444.png",
            ),
        ],
    )
    _roundtrip(meta)


def test_raster_meta_empty_levels() -> None:
    meta = RasterMetaV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        source_pdf_sha256="",
    )
    _roundtrip(meta)
    assert meta.levels == []


def test_raster_meta_json_schema() -> None:
    schema = RasterMetaV1.model_json_schema()
    assert schema["properties"]["schema_version"]["default"] == "raster_meta.v1"
    assert "levels" in schema["properties"]
    assert schema["properties"]["page_id"]["pattern"] == r"^p\d{4}$"

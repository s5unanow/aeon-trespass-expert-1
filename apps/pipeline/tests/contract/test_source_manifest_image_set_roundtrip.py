"""Roundtrip tests for the image-set source schemas (S5U-1536).

Split out of test_schema_roundtrip.py (a grandfathered 400+ line file that must
not grow) so the image-set additions live in a focused, sub-ceiling module.
"""

import json

from pydantic import BaseModel

from atr_schemas.image_set_manifest_v1 import (
    CaptureMetadata,
    ImageSetImageEntry,
    ImageSetManifestV1,
)
from atr_schemas.source_manifest_v1 import PageEntry, SourceImageRef, SourceManifestV1


def _roundtrip[M: BaseModel](model_instance: M) -> None:
    model_cls = type(model_instance)
    json_str = model_instance.model_dump_json()
    restored = model_cls.model_validate(json.loads(json_str))
    assert restored == model_instance


def test_source_manifest_image_set_roundtrip() -> None:
    manifest = SourceManifestV1(
        document_id="tiny_image_set",
        source_kind="image_set",
        source_image_set_sha256="d" * 64,
        page_count=1,
        pages=[PageEntry(page_id="p0001", page_number=1)],
        images=[
            SourceImageRef(
                image_id="page_01_a",
                sha256="a" * 64,
                page_number=1,
                media_type="image/png",
                extension=".png",
                width_px=16,
                height_px=16,
                artifact_ref="tiny_image_set/source_image/page/page_01_a/abc123def456.png",
            )
        ],
    )
    _roundtrip(manifest)


def test_image_set_manifest_roundtrip() -> None:
    manifest = ImageSetManifestV1(
        document_id="tiny_image_set",
        images=[
            ImageSetImageEntry(
                image_id="page_01_a",
                path="images/page_01_a.png",
                page_number=1,
                media_type="image/png",
                capture=CaptureMetadata(
                    camera_make="Synthetic",
                    camera_model="atr-fixture",
                    captured_at="2026-07-09T00:00:00Z",
                    orientation=1,
                    exif={"ISO": "100"},
                ),
            ),
            ImageSetImageEntry(image_id="page_02_a", path="images/page_02_a.png", page_number=2),
        ],
    )
    _roundtrip(manifest)

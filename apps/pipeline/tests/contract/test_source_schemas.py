"""Contract tests for source abstraction schemas."""

from __future__ import annotations

import json

from atr_schemas.image_set_manifest_v1 import ImageSetImageV1, ImageSetManifestV1
from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1


def test_image_set_manifest_roundtrip() -> None:
    manifest = ImageSetManifestV1(
        images=[
            ImageSetImageV1(
                image_id="img.p0001.aaaaaaaaaaaa",
                page_id="p0001",
                page_number=1,
                path="source/page-001.png",
                media_type="image/png",
                sha256="a" * 64,
                capture={"device": "test camera"},
                exif={"DateTimeOriginal": "2026:07:09 10:00:00"},
            )
        ]
    )

    restored = ImageSetManifestV1.model_validate(json.loads(manifest.model_dump_json()))

    assert restored == manifest


def test_source_manifest_image_set_roundtrip() -> None:
    manifest = SourceManifestV1(
        document_id="image_doc",
        source_kind="image_set",
        source_pdf_sha256="",
        source_image_set_sha256="b" * 64,
        source_image_set_manifest_sha256="c" * 64,
        page_count=1,
        pages=[
            PageEntry(
                page_id="p0001",
                page_number=1,
                source_image_id="img.p0001.aaaaaaaaaaaa",
                raw_image_ref="image_doc/raw_image/page/img.p0001.aaaaaaaaaaaa/hash.png",
            )
        ],
        image_set=ImageSetManifestV1(
            images=[
                ImageSetImageV1(
                    image_id="img.p0001.aaaaaaaaaaaa",
                    page_id="p0001",
                    page_number=1,
                    path="source/page-001.png",
                    media_type="image/png",
                    sha256="a" * 64,
                )
            ]
        ),
    )

    restored = SourceManifestV1.model_validate(json.loads(manifest.model_dump_json()))

    assert restored == manifest
    assert restored.source_pdf_sha256 == ""

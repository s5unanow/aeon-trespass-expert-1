"""Contracts for image-set input manifests and source identity output."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from atr_schemas.image_set_manifest_v1 import ImageSetManifestV1
from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64

VALID_IMAGE_SET: dict[str, object] = {
    "schema_version": "image_set_manifest.v1",
    "images": [
        {
            "image_id": "img.page-0001",
            "path": "page_0001.png",
            "media_type": "image/png",
            "sha256": SHA_A,
            "page_id": "p0001",
            "page_number": 1,
            "capture": {
                "captured_at": "2026-07-10T09:30:00Z",
                "camera_make": "Synthetic",
                "camera_model": "Fixture",
                "exif_orientation": 1,
            },
        },
        {
            "image_id": "img.page-0002",
            "path": "page_0002.jpg",
            "media_type": "image/jpeg",
            "sha256": SHA_B,
            "page_id": "p0002",
            "page_number": 2,
        },
    ],
}


def _valid_source_manifest() -> dict[str, object]:
    return {
        "document_id": "photos",
        "source_kind": "image_set",
        "source_pdf_sha256": "",
        "source_manifest_sha256": SHA_C,
        "source_image_set_sha256": SHA_D,
        "page_count": 2,
        "pages": [
            {"page_id": "p0001", "page_number": 1},
            {"page_id": "p0002", "page_number": 2},
        ],
        "source_images": [
            {
                "image_id": "img.page-0001",
                "page_id": "p0001",
                "page_number": 1,
                "media_type": "image/png",
                "sha256": SHA_A,
                "raw_artifact_ref": ("photos/raw_image/page/img.page-0001/aaaaaaaaaaaa.png"),
            },
            {
                "image_id": "img.page-0002",
                "page_id": "p0002",
                "page_number": 2,
                "media_type": "image/jpeg",
                "sha256": SHA_B,
                "raw_artifact_ref": ("photos/raw_image/page/img.page-0002/bbbbbbbbbbbb.jpg"),
            },
        ],
    }


def test_image_set_manifest_roundtrips_with_capture_metadata() -> None:
    manifest = ImageSetManifestV1.model_validate(VALID_IMAGE_SET)

    restored = ImageSetManifestV1.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert restored.images[0].capture.camera_model == "Fixture"
    assert restored.images[0].capture.exif_orientation == 1


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("image_id", "img.page-0001", "duplicate image_id"),
        ("path", "page_0001.png", "duplicate image path"),
        ("page_id", "p0001", "page mapping"),
    ],
)
def test_image_set_manifest_rejects_duplicate_entries(
    field: str,
    replacement: str,
    message: str,
) -> None:
    payload = deepcopy(VALID_IMAGE_SET)
    images = payload["images"]
    assert isinstance(images, list)
    second = images[1]
    assert isinstance(second, dict)
    second[field] = replacement

    with pytest.raises(ValidationError, match=message):
        ImageSetManifestV1.model_validate(payload)


def test_image_set_manifest_rejects_non_contiguous_page_order() -> None:
    payload = deepcopy(VALID_IMAGE_SET)
    images = payload["images"]
    assert isinstance(images, list)
    second = images[1]
    assert isinstance(second, dict)
    second["page_number"] = 3
    second["page_id"] = "p0003"

    with pytest.raises(ValidationError, match="contiguous"):
        ImageSetManifestV1.model_validate(payload)


def test_image_set_manifest_rejects_page_id_number_mismatch() -> None:
    payload = deepcopy(VALID_IMAGE_SET)
    images = payload["images"]
    assert isinstance(images, list)
    first = images[0]
    assert isinstance(first, dict)
    first["page_id"] = "p0003"

    with pytest.raises(ValidationError, match="must match page_number"):
        ImageSetManifestV1.model_validate(payload)


def test_image_set_source_manifest_roundtrips_without_pdf_hash() -> None:
    manifest = SourceManifestV1.model_validate(_valid_source_manifest())

    restored = SourceManifestV1.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert restored.source_kind == "image_set"
    assert restored.source_pdf_sha256 == ""
    assert restored.source_image_set_sha256 == SHA_D
    assert [entry.page_id for entry in restored.source_images] == ["p0001", "p0002"]


def test_image_set_source_manifest_rejects_pdf_hash_overload() -> None:
    payload = _valid_source_manifest()
    payload["source_pdf_sha256"] = SHA_A

    with pytest.raises(ValidationError, match="source_pdf_sha256 must be empty"):
        SourceManifestV1.model_validate(payload)


def test_pdf_source_manifest_rejects_image_set_fingerprints() -> None:
    with pytest.raises(ValidationError, match="image-set fields must be empty"):
        SourceManifestV1(
            document_id="pdf",
            source_kind="pdf",
            source_pdf_sha256=SHA_A,
            source_manifest_sha256=SHA_C,
            source_image_set_sha256=SHA_D,
            page_count=1,
            pages=[PageEntry(page_id="p0001", page_number=1)],
        )


def test_existing_pdf_manifest_defaults_to_pdf_source_kind() -> None:
    manifest = SourceManifestV1(
        document_id="legacy",
        source_pdf_sha256="abc123",
        page_count=1,
        pages=[PageEntry(page_id="p0001", page_number=1)],
    )

    assert manifest.source_kind == "pdf"
    assert manifest.source_pdf_sha256 == "abc123"
    assert manifest.source_images == []


def test_source_manifest_rejects_unknown_source_kind() -> None:
    payload = _valid_source_manifest()
    payload["source_kind"] = "scanner"

    with pytest.raises(ValidationError, match="source_kind"):
        SourceManifestV1.model_validate(payload)

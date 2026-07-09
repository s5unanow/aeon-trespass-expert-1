"""Source abstraction config tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atr_pipeline.config.models import DocumentConfig


def test_legacy_source_pdf_normalizes_to_pdf_source() -> None:
    doc = DocumentConfig(id="legacy_doc", source_pdf="materials/source.pdf")

    assert doc.source.source_kind == "pdf"
    assert doc.source.source_pdf == "materials/source.pdf"
    assert doc.source_pdf == "materials/source.pdf"


def test_image_set_source_config_validates_through_union() -> None:
    doc = DocumentConfig.model_validate(
        {
            "id": "image_doc",
            "source_kind": "image_set",
            "image_set_manifest": (
                "packages/fixtures/sample_documents/image_set_smoke/source/manifest.json"
            ),
        }
    )

    assert doc.source.source_kind == "image_set"
    assert doc.source.manifest_path.endswith("manifest.json")
    assert doc.source_pdf == ""


def test_unknown_source_kind_fails_closed() -> None:
    with pytest.raises(ValidationError, match="source_kind"):
        DocumentConfig.model_validate(
            {
                "id": "bad_doc",
                "source_kind": "scanner",
                "image_set_manifest": "source/manifest.json",
            }
        )

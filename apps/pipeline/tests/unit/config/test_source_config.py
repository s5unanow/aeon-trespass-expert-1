"""Source-kind configuration and legacy PDF compatibility contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from atr_pipeline.config import load_document_config
from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_legacy_source_pdf_normalizes_to_pdf_variant() -> None:
    config = DocumentConfig(id="legacy", source_pdf="materials/book.pdf")

    assert config.source.source_kind == "pdf"
    assert config.source.path == "materials/book.pdf"
    assert config.source_pdf == "materials/book.pdf"


def test_current_pdf_config_keeps_resolved_path_behavior() -> None:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())

    assert config.document.source.source_kind == "pdf"
    assert config.source_pdf_path == (
        _repo_root()
        / "packages/fixtures/sample_documents/walking_skeleton/source/sample_page_01.pdf"
    )


def test_explicit_image_set_source_validates() -> None:
    config = DocumentConfig.model_validate(
        {
            "id": "photos",
            "source": {
                "source_kind": "image_set",
                "manifest_path": "materials/photos/manifest.json",
            },
        }
    )

    assert config.source.source_kind == "image_set"
    assert config.source.manifest_path == "materials/photos/manifest.json"
    assert config.source_pdf is None


def test_flat_image_set_config_normalizes_to_union() -> None:
    config = DocumentConfig.model_validate(
        {
            "id": "photos",
            "source_kind": "image_set",
            "source_manifest": "materials/photos/manifest.json",
        }
    )

    assert config.source.source_kind == "image_set"
    assert config.source.manifest_path == "materials/photos/manifest.json"


def test_image_set_manifest_path_resolves_from_repo_root(tmp_path: Path) -> None:
    config = DocumentBuildConfig.model_validate(
        {
            "document": {
                "id": "photos",
                "source_kind": "image_set",
                "source_manifest": "materials/photos/manifest.json",
            },
            "repo_root": tmp_path,
        }
    )

    assert config.source_manifest_path == tmp_path / "materials/photos/manifest.json"
    with pytest.raises(ValueError, match="does not use a PDF"):
        _ = config.source_pdf_path


def test_unknown_source_kind_fails_closed() -> None:
    with pytest.raises(ValidationError, match="source_kind"):
        DocumentConfig.model_validate(
            {
                "id": "bad",
                "source": {
                    "source_kind": "scanner",
                    "manifest_path": "materials/photos/manifest.json",
                },
            }
        )

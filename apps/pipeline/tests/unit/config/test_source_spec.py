"""Tests for the document source abstraction (source_kind union, S5U-1536)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from atr_pipeline.config import load_document_config
from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig
from atr_pipeline.config.source import ImageSetSource, PdfSource


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


# --- Legacy source_pdf backward compatibility (criterion 2) ---


def test_legacy_source_pdf_normalizes_to_pdf_variant() -> None:
    """A config using the legacy `source_pdf` string resolves to a PdfSource."""
    doc = DocumentConfig(id="d", source_pdf="materials/x.pdf")
    spec = doc.resolved_source
    assert isinstance(spec, PdfSource)
    assert spec.source_kind == "pdf"
    assert spec.source_pdf == "materials/x.pdf"


def test_walking_skeleton_config_resolves_pdf_source_and_path() -> None:
    """The real walking_skeleton config produces a PDF variant with the same path."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    assert cfg.document.resolved_source.source_kind == "pdf"
    assert cfg.source_pdf_path.is_absolute()
    assert cfg.source_pdf_path.name == "sample_page_01.pdf"


def test_source_pdf_path_honors_post_load_mutation() -> None:
    """resolved_source is re-derived each access, so mutating source_pdf is honored.

    This guards the existing test_stage_cache_pdf_content pattern that overrides
    `config.document.source_pdf` after load.
    """
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    cfg.document.source_pdf = "/tmp/other.pdf"
    assert cfg.source_pdf_path == Path("/tmp/other.pdf")


# --- Image-set variant validation ---


def test_image_set_source_validates_through_union() -> None:
    doc = DocumentConfig.model_validate(
        {"id": "d", "source": {"source_kind": "image_set", "manifest": "m.toml"}}
    )
    spec = doc.resolved_source
    assert isinstance(spec, ImageSetSource)
    assert spec.manifest == "m.toml"


def test_image_set_manifest_path_resolves() -> None:
    cfg = load_document_config("tiny_image_set", repo_root=_repo_root())
    assert cfg.document.resolved_source.source_kind == "image_set"
    assert cfg.image_set_manifest_path.is_absolute()
    assert cfg.image_set_manifest_path.name == "manifest.toml"


# --- Fail-closed cases (criterion 4 + exactly-one-of) ---


def test_unknown_source_kind_fails_closed_at_load() -> None:
    with pytest.raises(ValidationError) as excinfo:
        DocumentConfig.model_validate(
            {"id": "d", "source": {"source_kind": "video", "manifest": "m.toml"}}
        )
    # The discriminator error names the offending tag and the valid tags.
    assert "video" in str(excinfo.value)


def test_both_sources_set_fails_closed() -> None:
    with pytest.raises(ValidationError, match="not both"):
        DocumentConfig.model_validate(
            {
                "id": "d",
                "source_pdf": "x.pdf",
                "source": {"source_kind": "image_set", "manifest": "m.toml"},
            }
        )


def test_no_source_set_fails_closed() -> None:
    with pytest.raises(ValidationError, match="must specify a source"):
        DocumentConfig.model_validate({"id": "d"})


# --- Cross-kind accessor guards ---


def _build_config(document: DocumentConfig) -> DocumentBuildConfig:
    return DocumentBuildConfig(document=document, repo_root=_repo_root())


def test_source_pdf_path_raises_for_image_set() -> None:
    cfg = _build_config(
        DocumentConfig(id="d", source=ImageSetSource(manifest="m.toml")),
    )
    with pytest.raises(ValueError, match="not 'pdf'"):
        _ = cfg.source_pdf_path


def test_image_set_manifest_path_raises_for_pdf() -> None:
    cfg = _build_config(DocumentConfig(id="d", source_pdf="x.pdf"))
    with pytest.raises(ValueError, match="not 'image_set'"):
        _ = cfg.image_set_manifest_path

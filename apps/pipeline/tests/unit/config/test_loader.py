"""Tests for the layered config loader."""

from pathlib import Path

import pytest

from atr_pipeline.config.loader import load_document_config


def _repo_root() -> Path:
    """Return the repo root for tests."""
    return Path(__file__).resolve().parents[5]


def test_load_walking_skeleton_config() -> None:
    """Base + document config loads and resolves correctly."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    assert cfg.document.id == "walking_skeleton"
    assert cfg.document.source_lang == "en"
    assert "ru" in cfg.document.target_langs
    assert cfg.pipeline.version == "0.1.0"
    assert cfg.symbols.match_threshold == 0.93
    assert cfg.document.structure_builder == "simple"
    assert cfg.translation.provider == "mock"


def test_config_resolves_paths() -> None:
    """Paths are resolved relative to repo root."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    assert cfg.source_pdf_path.is_absolute()
    assert cfg.source_pdf_path.name == "sample_page_01.pdf"
    catalog_path = cfg.symbol_catalog_path
    assert catalog_path is not None
    assert catalog_path.is_absolute()
    assert catalog_path.name == "walking_skeleton.symbols.toml"


def test_ci_env_overlay() -> None:
    """CI overlay reduces parallelism and uses mock provider."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root(), env="ci")
    assert cfg.pipeline.parallelism == 2
    assert cfg.translation.provider == "mock"


def test_missing_document_raises() -> None:
    """Missing document config raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Document config not found"):
        load_document_config("nonexistent_document", repo_root=_repo_root())


def test_deep_merge_preserves_base_defaults() -> None:
    """Document config overrides only what it sets; base defaults survive."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    # extraction.native.engine comes from base, not overridden by walking_skeleton
    assert cfg.extraction.native.engine == "pymupdf"
    # extraction.layout.dpi comes from base
    assert cfg.extraction.layout.dpi == 300

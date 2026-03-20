"""Tests for the layered config loader."""

from pathlib import Path

import pytest

from atr_pipeline.config.loader import _find_repo_root, load_document_config


def _repo_root() -> Path:
    """Return the repo root for tests."""
    return Path(__file__).resolve().parents[5]


def test_find_repo_root_from_monorepo_root() -> None:
    """_find_repo_root returns monorepo root when started there."""
    root = _repo_root()
    assert _find_repo_root(root) == root


def test_find_repo_root_from_nested_subproject() -> None:
    """_find_repo_root skips apps/pipeline/pyproject.toml and finds monorepo root."""
    root = _repo_root()
    nested = root / "apps" / "pipeline"
    assert nested.exists(), f"Expected {nested} to exist"
    resolved = _find_repo_root(nested)
    assert resolved == root, (
        f"Expected monorepo root {root}, got {resolved} (likely stopped at nested pyproject.toml)"
    )


def test_find_repo_root_from_deep_subdir() -> None:
    """_find_repo_root works from a deeply nested directory."""
    root = _repo_root()
    deep = root / "apps" / "pipeline" / "src" / "atr_pipeline"
    assert deep.exists()
    assert _find_repo_root(deep) == root


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


def test_structure_config_loaded_from_base_toml() -> None:
    """Structure section in base.toml populates StructureConfig."""
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    assert cfg.structure.footer_y_threshold == 790.0
    assert cfg.structure.body_font == "Adonis-Regular"
    assert cfg.structure.paragraph_gap_factor == 1.5
    assert cfg.structure.figure_min_width_pt == 100.0
    assert "GreenleafLightPro" in cfg.structure.heading_fonts


def test_structure_config_document_override() -> None:
    """Document config can override individual structure values."""
    cfg = load_document_config("ato_core_v1_1", repo_root=_repo_root())
    # Overridden in ato_core_v1_1.toml
    assert cfg.structure.footer_y_threshold == 785.0
    # Base defaults preserved for non-overridden fields
    assert cfg.structure.body_font == "Adonis-Regular"
    assert cfg.structure.paragraph_gap_factor == 1.5

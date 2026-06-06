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


def test_ato_core_s5u706_presentation_mode_overrides() -> None:
    """S5U-706 — p0040/p0067/p0074 flip to article; p0082 stays facsimile.

    p0040 (movement-example prose), p0067 (Ranged/Reach/Reflex keyword rules),
    and p0074 (Hekaton/Cyclonus tile-requirement lists) render as readable
    article content, so each carries an explicit ``presentation_mode = "article"``
    override (removing the override is not enough — the auto heuristic still
    classifies these hard/low-coverage pages as facsimile). p0082 is the
    "in-game Symbols" glossary whose multi-column icon-to-label grid cannot
    survive structure recovery, so it keeps its facsimile override.

    The well-facsimile pages (p0006/p0007) and the S5U-699 article pages
    (p0075/p0076) are pinned here as no-regression anchors.
    """
    cfg = load_document_config("ato_core_v1_1", repo_root=_repo_root())
    overrides = cfg.render.page_overrides

    # Flipped to article by S5U-706.
    for pid in ("p0040", "p0067", "p0074"):
        assert pid in overrides, f"{pid} override missing"
        assert overrides[pid].presentation_mode == "article", f"{pid} must be article after S5U-706"

    # Genuinely image-dominant — must stay facsimile.
    assert overrides["p0082"].presentation_mode == "facsimile"
    assert overrides["p0006"].presentation_mode == "facsimile"
    assert overrides["p0007"].presentation_mode == "facsimile"

    # S5U-699 article pages — must not regress.
    assert overrides["p0075"].presentation_mode == "article"
    assert overrides["p0076"].presentation_mode == "article"


def test_ato_core_facsimile_allowlist_excludes_flipped_pages() -> None:
    """S5U-706 — the publish-guard facsimile allowlist no longer contains the
    flipped pages, so the S5U-699 guard would re-trip if their substantial
    payload were re-marked facsimile.

    Mirrors ``scripts/export_to_web.py::_load_facsimile_override_pids``: the
    allowlist is exactly the set of pages whose override is facsimile.
    """
    cfg = load_document_config("ato_core_v1_1", repo_root=_repo_root())
    facsimile_pids = {
        pid for pid, ov in cfg.render.page_overrides.items() if ov.presentation_mode == "facsimile"
    }
    # Flipped pages must NOT be allowlisted any more.
    assert facsimile_pids.isdisjoint({"p0040", "p0067", "p0074"})
    # p0082 and the genuine facsimile pages remain allowlisted.
    assert {"p0006", "p0007", "p0082"} <= facsimile_pids


def test_ato_core_inherits_codex_cli_translation_defaults() -> None:
    """S5U-747 — ato_core_v1_1 picks up codex-cli flat keys from base.toml
    and codex-specific provider_options from its own document config."""
    cfg = load_document_config("ato_core_v1_1", repo_root=_repo_root())
    assert cfg.translation.provider == "codex-cli"
    assert cfg.translation.model_default == "gpt-5.5"
    assert cfg.translation.model_hard == "gpt-5.5"
    assert cfg.translation.fallback_provider == "gemini-cli"
    assert cfg.translation.fallback_model == "gemini-2.5-flash"
    assert cfg.translation.provider_options.cli.reasoning_effort == "xhigh"
    assert cfg.translation.provider_options.cli.sandbox == "read-only"
    assert cfg.translation.provider_options.cli.approval_policy == "never"
    assert cfg.translation.provider_options.cli.timeout_seconds == 600


def test_fixture_documents_override_to_mock_without_codex_options() -> None:
    """Mock-using fixture documents override ``provider`` cleanly — they do
    NOT inherit any non-default ``provider_options`` from base.toml.

    Regression-pin on the S5U-747 design: provider_options.cli MUST live in
    the per-document config, not base.toml, so the factory's
    "mock accepts no provider options" rule does not fire on fixture runs.
    """
    cfg = load_document_config("walking_skeleton", repo_root=_repo_root())
    assert cfg.translation.provider == "mock"
    # No CLI options inherited — the namespace is at its Pydantic default.
    assert cfg.translation.provider_options.cli.reasoning_effort is None
    assert cfg.translation.provider_options.cli.sandbox is None
    assert cfg.translation.provider_options.cli.approval_policy is None
    # And the factory accepts this config without raising.
    from atr_pipeline.services.llm.factory import create_translator

    adapter = create_translator(cfg.translation)
    assert type(adapter).__name__ == "MockTranslator"

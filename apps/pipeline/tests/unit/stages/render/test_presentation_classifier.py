"""Tests for presentation mode classification."""

from __future__ import annotations

from atr_pipeline.config.models import PageOverride
from atr_pipeline.stages.render.presentation_classifier import classify_presentation_mode
from atr_schemas.layout_page_v1 import DifficultyScoreV1


def _make_difficulty(
    *,
    hard_page: bool = False,
    native_text_coverage: float = 1.0,
) -> DifficultyScoreV1:
    return DifficultyScoreV1(
        page_id="p0007",
        hard_page=hard_page,
        native_text_coverage=native_text_coverage,
    )


def test_explicit_override_facsimile() -> None:
    """Config override wins over auto-classification."""
    overrides = {"p0007": PageOverride(presentation_mode="facsimile")}
    difficulty = _make_difficulty(hard_page=False, native_text_coverage=0.9)
    result = classify_presentation_mode("p0007", difficulty, 0.15, overrides)
    assert result == "facsimile"


def test_explicit_override_article_on_low_coverage() -> None:
    """Explicit article override prevents facsimile even with low coverage."""
    overrides = {"p0007": PageOverride(presentation_mode="article")}
    difficulty = _make_difficulty(hard_page=True, native_text_coverage=0.05)
    result = classify_presentation_mode("p0007", difficulty, 0.15, overrides)
    assert result == "article"


def test_auto_facsimile_hard_page_low_coverage() -> None:
    """Auto heuristic: hard_page + coverage below threshold -> facsimile."""
    difficulty = _make_difficulty(hard_page=True, native_text_coverage=0.08)
    result = classify_presentation_mode("p0007", difficulty, 0.15, {})
    assert result == "facsimile"


def test_auto_article_hard_page_high_coverage() -> None:
    """Hard page with coverage above threshold stays article."""
    difficulty = _make_difficulty(hard_page=True, native_text_coverage=0.5)
    result = classify_presentation_mode("p0007", difficulty, 0.15, {})
    assert result == "article"


def test_auto_article_not_hard_page() -> None:
    """Low coverage alone without hard_page stays article."""
    difficulty = _make_difficulty(hard_page=False, native_text_coverage=0.05)
    result = classify_presentation_mode("p0007", difficulty, 0.15, {})
    assert result == "article"


def test_missing_difficulty_defaults_article() -> None:
    """Missing difficulty data -> article."""
    result = classify_presentation_mode("p0007", None, 0.15, {})
    assert result == "article"


def test_override_title_only_does_not_set_mode() -> None:
    """Override with title but no presentation_mode doesn't change mode."""
    overrides = {"p0007": PageOverride(title="Components")}
    result = classify_presentation_mode("p0007", None, 0.15, overrides)
    assert result == "article"

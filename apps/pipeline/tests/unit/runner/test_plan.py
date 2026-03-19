"""Tests for pipeline plan and stage resolution."""

from __future__ import annotations

import pytest

from atr_pipeline.runner.plan import (
    SOURCE_ONLY_STAGES,
    WALKING_SKELETON_STAGES,
    resolve_stage_range,
)


def test_default_stage_range_returns_all() -> None:
    """Default plan returns the full walking skeleton."""
    stages = resolve_stage_range(from_stage="ingest", to_stage="publish")
    assert stages == WALKING_SKELETON_STAGES


def test_default_includes_translate() -> None:
    """Default plan includes the translate stage."""
    stages = resolve_stage_range()
    assert "translate" in stages


def test_edition_en_excludes_translate() -> None:
    """Source-only edition excludes the translate stage."""
    stages = resolve_stage_range(edition="en")
    assert "translate" not in stages
    assert stages == SOURCE_ONLY_STAGES


def test_edition_en_preserves_order() -> None:
    """Source-only stages are in the correct order."""
    stages = resolve_stage_range(edition="en")
    assert stages.index("structure") < stages.index("render")
    assert stages.index("render") < stages.index("qa")


def test_edition_en_with_range() -> None:
    """Source-only with --from/--to works correctly."""
    stages = resolve_stage_range(from_stage="structure", to_stage="qa", edition="en")
    assert stages == ["structure", "render", "qa"]
    assert "translate" not in stages


def test_edition_all_includes_translate() -> None:
    """Explicit 'all' edition includes translate."""
    stages = resolve_stage_range(edition="all")
    assert "translate" in stages


def test_unknown_stage_raises() -> None:
    """Unknown stage name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown stage"):
        resolve_stage_range(from_stage="nonexistent")

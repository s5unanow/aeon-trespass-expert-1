"""S5U-1555 translation-hardness configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.config.translation_hardness import TranslationHardnessConfig


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_translation_hardness_defaults_disabled() -> None:
    """Existing configs retain the legacy routing path by default."""
    config = TranslationConfig(provider="mock", fallback_provider="")

    assert config.hardness.enabled is False


def test_translation_hardness_loads_from_toml() -> None:
    """All routing weights and the threshold are TOML-configurable."""
    config = load_document_config("walking_skeleton", repo_root=_repo_root())

    assert config.translation.hardness.enabled is False
    assert config.translation.hardness.threshold == 2.0
    assert config.translation.hardness.inline_icon_density_weight == 2.0
    assert config.translation.hardness.cross_reference_density_weight == 2.0
    assert config.translation.hardness.table_presence_weight == 1.0
    assert config.translation.hardness.segment_count_weight == 0.05
    assert config.translation.hardness.segment_length_weight == 0.001


def test_translation_hardness_rejects_unknown_toml_key() -> None:
    """A typo in ``[translation.hardness]`` fails config validation."""
    with pytest.raises(ValueError, match="threshhold"):
        TranslationHardnessConfig(threshhold=1.0)  # type: ignore[call-arg]


def test_translation_hardness_rejects_negative_threshold() -> None:
    """The routing threshold cannot be negative."""
    with pytest.raises(ValueError):
        TranslationHardnessConfig(threshold=-0.01)


def test_translation_hardness_rejects_negative_weight() -> None:
    """Signal weights cannot be negative."""
    with pytest.raises(ValueError):
        TranslationHardnessConfig(inline_icon_density_weight=-0.01)


def test_translation_hardness_rejects_non_finite_values() -> None:
    """NaN and infinity cannot poison score arithmetic or JSON provenance."""
    with pytest.raises(ValueError):
        TranslationHardnessConfig(threshold=float("nan"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(threshold=float("inf"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(inline_icon_density_weight=float("inf"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(cross_reference_density_weight=float("inf"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(table_presence_weight=float("inf"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(segment_count_weight=float("inf"))
    with pytest.raises(ValueError):
        TranslationHardnessConfig(segment_length_weight=float("inf"))

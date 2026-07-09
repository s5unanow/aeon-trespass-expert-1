"""S5U-1555 translation-hardness configuration tests."""

from __future__ import annotations

import tomllib

import pytest

from atr_pipeline.config.models import TranslationConfig


def test_translation_hardness_defaults_disabled() -> None:
    """Existing configs retain the legacy routing path by default."""
    config = TranslationConfig(provider="mock", fallback_provider="")

    assert config.hardness.enabled is False


def test_translation_hardness_loads_from_toml() -> None:
    """All routing weights and the threshold are TOML-configurable."""
    data = tomllib.loads(
        """
        [translation]
        provider = "mock"
        fallback_provider = ""

        [translation.hardness]
        enabled = true
        threshold = 2.5
        inline_icon_density_weight = 3.0
        cross_reference_density_weight = 4.0
        table_presence_weight = 5.0
        segment_count_weight = 0.25
        segment_length_weight = 0.01
        """
    )

    config = TranslationConfig.model_validate(data["translation"])

    assert config.hardness.enabled is True
    assert config.hardness.threshold == 2.5
    assert config.hardness.inline_icon_density_weight == 3.0
    assert config.hardness.cross_reference_density_weight == 4.0
    assert config.hardness.table_presence_weight == 5.0
    assert config.hardness.segment_count_weight == 0.25
    assert config.hardness.segment_length_weight == 0.01


def test_translation_hardness_rejects_unknown_toml_key() -> None:
    """A typo in ``[translation.hardness]`` fails config validation."""
    data = tomllib.loads(
        """
        [translation]
        provider = "mock"
        fallback_provider = ""

        [translation.hardness]
        enabled = true
        threshhold = 1.0
        """
    )

    with pytest.raises(ValueError, match="threshhold"):
        TranslationConfig.model_validate(data["translation"])


@pytest.mark.parametrize("field", ["threshold", "inline_icon_density_weight"])
def test_translation_hardness_rejects_negative_values(field: str) -> None:
    """Scores cannot be configured with negative thresholds or weights."""
    with pytest.raises(ValueError):
        TranslationConfig.model_validate(
            {
                "provider": "mock",
                "fallback_provider": "",
                "hardness": {field: -0.01},
            }
        )

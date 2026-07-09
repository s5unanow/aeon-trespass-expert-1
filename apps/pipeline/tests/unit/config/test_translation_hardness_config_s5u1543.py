"""S5U-1543 translation hardness config validation tests."""

from __future__ import annotations

import pytest

from atr_pipeline.config.models import TranslationConfig


def test_translation_hardness_defaults_disabled() -> None:
    """Hardness routing is opt-in so existing configs keep old behavior."""
    config = TranslationConfig(provider="mock", fallback_provider="")

    assert config.hardness.enabled is False


def test_translation_hardness_rejects_unknown_keys() -> None:
    """Unknown hardness keys fail config load under extra='forbid'."""
    with pytest.raises(ValueError, match="unexpected_knob"):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            hardness={"enabled": True, "unexpected_knob": 1},
        )


def test_translation_hardness_rejects_unknown_weight_keys() -> None:
    """Unknown nested weight keys fail config load under extra='forbid'."""
    with pytest.raises(ValueError, match="unknown_weight"):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            hardness={"enabled": True, "weights": {"unknown_weight": 1.0}},
        )

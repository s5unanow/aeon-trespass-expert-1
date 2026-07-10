"""S5U-1542 — ``[translation.hardness]`` config validation.

The hardness section drives per-page routing to ``model_hard``. It must:

* default to OFF so existing configs behave identically (byte-identical
  regression, AC 2);
* reject unknown keys (``extra="forbid"``) so a typo fails config load (AC 5);
* load from a nested TOML-shaped dict via the layered loader path
  (``DocumentBuildConfig.model_validate``);
* reject negative weights / threshold.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atr_pipeline.config.models import DocumentBuildConfig, TranslationConfig
from atr_pipeline.config.translation_hardness import TranslationHardnessConfig


def test_hardness_defaults_are_disabled() -> None:
    """A default ``TranslationConfig`` has hardness routing OFF."""
    cfg = TranslationConfig()
    assert cfg.hardness.enabled is False
    # A default hardness sub-config carries the documented starting weights.
    assert cfg.hardness == TranslationHardnessConfig()
    assert cfg.hardness.threshold >= 0.0


def test_hardness_rejects_unknown_key() -> None:
    """Unknown keys under ``[translation.hardness]`` fail config load (AC 5)."""
    with pytest.raises(ValidationError):
        TranslationHardnessConfig(enabled=True, wieght_icon_density=2.0)


def test_hardness_rejects_negative_weight() -> None:
    """Negative weights are rejected (weights are non-negative)."""
    with pytest.raises(ValidationError):
        TranslationHardnessConfig(weight_icon_density=-1.0)


def test_hardness_rejects_negative_threshold() -> None:
    """A negative threshold is rejected."""
    with pytest.raises(ValidationError):
        TranslationHardnessConfig(threshold=-0.1)


def test_hardness_loads_from_nested_document_config() -> None:
    """A nested ``translation.hardness`` dict loads via the loader path."""
    raw = {
        "document": {"id": "x", "source_pdf": "x.pdf"},
        "translation": {
            "provider": "mock",
            "fallback_provider": "",
            "hardness": {
                "enabled": True,
                "threshold": 3.5,
                "weight_icon_density": 2.0,
            },
        },
    }
    cfg = DocumentBuildConfig.model_validate(raw)
    assert cfg.translation.hardness.enabled is True
    assert cfg.translation.hardness.threshold == 3.5
    assert cfg.translation.hardness.weight_icon_density == 2.0


def test_hardness_unknown_key_via_document_config_fails() -> None:
    """An unknown hardness key surfaces at document-config load time (AC 5)."""
    raw = {
        "document": {"id": "x", "source_pdf": "x.pdf"},
        "translation": {
            "provider": "mock",
            "fallback_provider": "",
            "hardness": {"enabled": True, "bogus_knob": 1},
        },
    }
    with pytest.raises(ValidationError):
        DocumentBuildConfig.model_validate(raw)

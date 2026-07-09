"""S5U-1555 factory coverage for hard-primary model overrides."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm import factory
from atr_pipeline.services.llm.fallback import FallbackTranslator


def test_primary_model_override_preserves_configured_fallback_model() -> None:
    """Hard-page escalation changes only the primary side of the fallback chain."""
    config = TranslationConfig(
        provider="openai",
        model_default="easy-model",
        fallback_provider="anthropic",
        fallback_model="fallback-model",
    )
    primary = MagicMock()
    fallback = MagicMock()

    with patch.object(
        factory,
        "_create_single_adapter",
        side_effect=[primary, fallback],
    ) as create_adapter:
        adapter = factory.create_translator(
            config,
            primary_model_override="hard-model",
        )

    assert isinstance(adapter, FallbackTranslator)
    assert [call.args[1] for call in create_adapter.call_args_list] == [
        "hard-model",
        "fallback-model",
    ]

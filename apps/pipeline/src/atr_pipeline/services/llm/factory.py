"""Build a TranslatorAdapter from pipeline configuration."""

from __future__ import annotations

from atr_schemas.concept_registry_v1 import ConceptRegistryV1

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.base import TranslatorAdapter


def create_translator(
    config: TranslationConfig,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslatorAdapter:
    """Instantiate the adapter specified by *config.provider*."""
    provider = config.provider.lower()

    if provider == "mock":
        from atr_pipeline.services.llm.mock_translator import MockTranslator

        return MockTranslator()

    if provider == "openai":
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            model=config.model_default,
            temperature=config.temperature,
            concept_registry=concept_registry,
        )

    if provider == "anthropic":
        from atr_pipeline.services.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            model=config.model_default,
            temperature=config.temperature,
            concept_registry=concept_registry,
        )

    msg = f"Unknown translation provider: {provider!r}"
    raise ValueError(msg)

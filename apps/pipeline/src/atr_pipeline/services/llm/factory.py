"""Build a TranslatorAdapter from pipeline configuration."""

from __future__ import annotations

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_schemas.concept_registry_v1 import ConceptRegistryV1


def _create_single_adapter(
    provider: str,
    model: str,
    temperature: float,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslatorAdapter:
    """Instantiate a single adapter for the given *provider* name."""
    provider = provider.lower()

    if provider == "mock":
        from atr_pipeline.services.llm.mock_translator import MockTranslator

        return MockTranslator()

    if provider == "openai":
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            model=model,
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "anthropic":
        from atr_pipeline.services.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            model=model,
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "gemini":
        from atr_pipeline.services.llm.gemini_adapter import GeminiAdapter

        return GeminiAdapter(
            model=model or "gemini-2.5-flash",
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "gemini-cli":
        from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

        return GeminiCLIAdapter(
            model=model or "gemini-2.5-flash",
            concept_registry=concept_registry,
        )

    msg = f"Unknown translation provider: {provider!r}"
    raise ValueError(msg)


def create_translator(
    config: TranslationConfig,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslatorAdapter:
    """Instantiate the adapter specified by *config.provider*.

    When a ``fallback_provider`` is configured (and differs from the
    primary), the returned adapter is a :class:`FallbackTranslator` that
    retries the primary then falls back.  Mock providers skip fallback
    wrapping to keep test output deterministic.
    """
    primary = _create_single_adapter(
        config.provider,
        config.model_default,
        config.temperature,
        concept_registry,
    )

    use_fallback = (
        config.fallback_provider
        and config.fallback_provider.lower() != config.provider.lower()
        and config.provider.lower() != "mock"
    )

    if not use_fallback:
        return primary

    from atr_pipeline.services.llm.fallback import FallbackTranslator

    try:
        fallback = _create_single_adapter(
            config.fallback_provider,
            config.fallback_model,
            config.temperature,
            concept_registry,
        )
    except ValueError as exc:
        msg = f"Failed to create fallback provider: {exc}"
        raise ValueError(msg) from exc
    return FallbackTranslator(
        primary,
        fallback,
        max_retries=config.max_retries,
        retry_delay_seconds=config.retry_delay_seconds,
    )

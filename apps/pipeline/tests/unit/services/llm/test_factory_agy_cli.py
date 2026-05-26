"""Factory-side tests for the AGY CLI adapter."""

from __future__ import annotations

from atr_pipeline.config.models import (
    CLIProviderOptions,
    TranslationConfig,
    TranslationProviderOptions,
)
from atr_pipeline.services.llm.factory import create_translator


def test_factory_creates_agy_cli_adapter() -> None:
    config = TranslationConfig(
        provider="agy-cli",
        model_default="gemini-3-pro",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(timeout_seconds=900, reasoning_effort="high"),
        ),
    )

    adapter = create_translator(config)

    assert type(adapter).__name__ == "AgyCLIAdapter"
    assert adapter._model == "gemini-3-pro"  # type: ignore[attr-defined]
    assert adapter._reasoning_effort == "high"  # type: ignore[attr-defined]
    assert adapter._timeout == 900  # type: ignore[attr-defined]


def test_factory_agy_cli_case_insensitive() -> None:
    config = TranslationConfig(
        provider="AGY-CLI",
        model_default="gemini-3-pro",
        fallback_provider="",
    )

    adapter = create_translator(config)

    assert type(adapter).__name__ == "AgyCLIAdapter"


def test_factory_rejects_agy_unsupported_cli_options() -> None:
    import pytest

    config = TranslationConfig(
        provider="agy-cli",
        model_default="gemini-3-pro",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(sandbox="workspace-write"),
        ),
    )

    with pytest.raises(ValueError, match=r"does not support.*sandbox"):
        create_translator(config)

"""Tests for translator factory provider selection and error paths."""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.config.models import (
    APIProviderOptions,
    CLIProviderOptions,
    TranslationConfig,
    TranslationProviderOptions,
)
from atr_pipeline.services.llm.factory import create_translator


def _mock_openai_module() -> ModuleType:
    mod = ModuleType("openai")
    mod.OpenAI = MagicMock()  # type: ignore[attr-defined]
    return mod


def _mock_anthropic_module() -> ModuleType:
    mod = ModuleType("anthropic")
    mod.Anthropic = MagicMock()  # type: ignore[attr-defined]
    return mod


def _mock_google_modules() -> dict[str, ModuleType]:
    google_mod = ModuleType("google")
    genai_mod = ModuleType("google.genai")
    genai_mod.Client = MagicMock()  # type: ignore[attr-defined]
    google_mod.genai = genai_mod  # type: ignore[attr-defined]
    return {"google": google_mod, "google.genai": genai_mod}


def test_factory_creates_openai_adapter() -> None:
    """Factory should instantiate OpenAIAdapter for provider='openai'."""
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(provider="openai", model_default="gpt-4o", fallback_provider="")
        adapter = create_translator(config)
    assert type(adapter).__name__ == "OpenAIAdapter"


def test_factory_creates_anthropic_adapter() -> None:
    """Factory should instantiate AnthropicAdapter for provider='anthropic'."""
    with patch.dict("sys.modules", {"anthropic": _mock_anthropic_module()}):
        config = TranslationConfig(
            provider="anthropic",
            model_default="claude-sonnet-4-6",
            fallback_provider="",
        )
        adapter = create_translator(config)
    assert type(adapter).__name__ == "AnthropicAdapter"


def test_factory_creates_gemini_adapter() -> None:
    """Factory should instantiate GeminiAdapter for provider='gemini'."""
    with patch.dict("sys.modules", _mock_google_modules()):
        config = TranslationConfig(
            provider="gemini",
            model_default="gemini-2.5-flash",
            fallback_provider="",
        )
        adapter = create_translator(config)
    assert type(adapter).__name__ == "GeminiAdapter"


def test_factory_is_case_insensitive() -> None:
    """Provider names should be matched case-insensitively."""
    for name in ("Mock", "MOCK", "mock"):
        config = TranslationConfig(provider=name)
        adapter = create_translator(config)
        assert type(adapter).__name__ == "MockTranslator"


def test_factory_passes_config_to_openai() -> None:
    """Factory must forward model_default and temperature to OpenAI adapter."""
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o-mini",
            temperature=0.5,
            fallback_provider="",
        )
        adapter = create_translator(config)
    assert adapter._model == "gpt-4o-mini"
    assert adapter._temperature == 0.5


def test_factory_passes_config_to_anthropic() -> None:
    """Factory must forward model_default and temperature to Anthropic adapter."""
    with patch.dict("sys.modules", {"anthropic": _mock_anthropic_module()}):
        config = TranslationConfig(
            provider="anthropic",
            model_default="claude-sonnet-4-6",
            temperature=0.3,
            fallback_provider="",
        )
        adapter = create_translator(config)
    assert adapter._model == "claude-sonnet-4-6"
    assert adapter._temperature == 0.3


def test_factory_rejects_unknown_provider() -> None:
    """Pydantic config validator rejects unknown providers before factory.

    The factory layer is also defensive against unknown providers (in case a
    caller bypasses the config model) but the canonical rejection path is
    Pydantic — that's the boundary all real callers cross.
    """
    with pytest.raises(ValueError, match="Unknown translation provider"):
        TranslationConfig(provider="nonexistent", fallback_provider="")


def test_factory_gemini_uses_fallback_model() -> None:
    """When model_default is empty, Gemini should get 'gemini-2.5-flash'."""
    with patch.dict("sys.modules", _mock_google_modules()):
        config = TranslationConfig(provider="gemini", model_default="", fallback_provider="")
        adapter = create_translator(config)
    assert adapter._model == "gemini-2.5-flash"


def test_factory_wraps_with_fallback() -> None:
    """When fallback_provider differs from primary, factory wraps in FallbackTranslator."""
    with patch.dict(
        "sys.modules",
        {"openai": _mock_openai_module(), "anthropic": _mock_anthropic_module()},
    ):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="anthropic",
            fallback_model="claude-sonnet-4-6",
        )
        adapter = create_translator(config)
    assert type(adapter).__name__ == "FallbackTranslator"


def test_factory_skips_fallback_for_mock() -> None:
    """Mock provider should not be wrapped with FallbackTranslator."""
    config = TranslationConfig(provider="mock", fallback_provider="anthropic")
    adapter = create_translator(config)
    assert type(adapter).__name__ == "MockTranslator"


def test_factory_skips_fallback_when_same_provider() -> None:
    """When fallback_provider matches primary, no wrapping occurs."""
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="openai",
        )
        adapter = create_translator(config)
    assert type(adapter).__name__ == "OpenAIAdapter"


def test_factory_creates_gemini_cli_adapter() -> None:
    """Factory should instantiate GeminiCLIAdapter for provider='gemini-cli'."""
    config = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
    )
    adapter = create_translator(config)
    assert type(adapter).__name__ == "GeminiCLIAdapter"


def test_factory_gemini_cli_uses_fallback_model() -> None:
    """When model_default is empty, gemini-cli should get 'gemini-2.5-flash'."""
    config = TranslationConfig(provider="gemini-cli", model_default="", fallback_provider="")
    adapter = create_translator(config)
    assert adapter._model == "gemini-2.5-flash"


# ── S5U-746 — Mock factory selection (explicit) ──────────────────────


def test_factory_creates_mock_adapter() -> None:
    """Factory should instantiate MockTranslator for provider='mock'."""
    config = TranslationConfig(provider="mock", fallback_provider="")
    adapter = create_translator(config)
    assert type(adapter).__name__ == "MockTranslator"


# ── S5U-746 — CLI provider options threading ─────────────────────────


def test_factory_threads_cli_timeout_to_gemini_cli() -> None:
    """``provider_options.cli.timeout_seconds`` is forwarded to GeminiCLIAdapter."""
    config = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(timeout_seconds=600),
        ),
    )
    adapter = create_translator(config)
    assert adapter._timeout == 600


def test_factory_uses_default_cli_timeout_when_unset() -> None:
    """Default CLI ``timeout_seconds`` of 300 is forwarded when unset."""
    config = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
    )
    adapter = create_translator(config)
    assert adapter._timeout == 300


# ── S5U-746 — Cross-provider option leakage rejected ─────────────────


def test_factory_rejects_cli_options_for_api_provider() -> None:
    """CLI options on an API provider are rejected at factory time.

    Pydantic accepts the config (the namespace exists on the model); the
    factory is the boundary that refuses option leakage. The error must
    name the offending namespace clearly.
    """
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="",
            provider_options=TranslationProviderOptions(
                cli=CLIProviderOptions(executable="/usr/local/bin/codex"),
            ),
        )
        with pytest.raises(ValueError, match=r"provider_options\.cli"):
            create_translator(config)


def test_factory_rejects_api_options_for_cli_provider() -> None:
    """API options on a CLI provider are rejected at factory time."""
    config = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            api=APIProviderOptions(api_key="sk-test"),
        ),
    )
    with pytest.raises(ValueError, match=r"provider_options\.api"):
        create_translator(config)


def test_factory_rejects_options_on_mock_provider() -> None:
    """Mock accepts no options — non-default values are rejected."""
    config = TranslationConfig(
        provider="mock",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(executable="/foo"),
        ),
    )
    with pytest.raises(ValueError, match="accepts no provider options"):
        create_translator(config)


def test_factory_rejects_cross_provider_options_in_fallback() -> None:
    """Same option-leakage rule applies to the fallback options namespace."""
    with patch.dict(
        "sys.modules",
        {"openai": _mock_openai_module(), "anthropic": _mock_anthropic_module()},
    ):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="anthropic",
            fallback_model="claude-sonnet-4-6",
            fallback_options=TranslationProviderOptions(
                cli=CLIProviderOptions(executable="/usr/local/bin/codex"),
            ),
        )
        with pytest.raises(ValueError, match=r"provider_options\.cli"):
            create_translator(config)


# Codex-CLI-specific factory tests live in ``test_factory_codex_cli.py``
# (split for the 400-line file ceiling). The remaining S5U-747 changes in
# *this* file are: removing the now-stale
# ``test_factory_rejects_codex_cli_until_adapter_lands`` test (the
# adapter is implemented now and the factory accepts ``codex-cli``).


# ── S5U-746 — Fallback wrapping with new options shape ───────────────


def test_factory_wraps_fallback_with_provider_options() -> None:
    """Primary CLI provider + API fallback both honour their options namespaces."""
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(
            provider="gemini-cli",
            model_default="gemini-2.5-flash",
            fallback_provider="openai",
            fallback_model="gpt-4o",
            provider_options=TranslationProviderOptions(
                cli=CLIProviderOptions(timeout_seconds=450),
            ),
            fallback_options=TranslationProviderOptions(
                api=APIProviderOptions(api_key="sk-test"),
            ),
        )
        adapter = create_translator(config)
    assert type(adapter).__name__ == "FallbackTranslator"
    assert adapter._primary._timeout == 450  # type: ignore[attr-defined]
    assert adapter._fallback._model == "gpt-4o"  # type: ignore[attr-defined]


def test_factory_skips_fallback_when_same_provider_case_insensitive() -> None:
    """``provider="OpenAI"`` and ``fallback_provider="openai"`` are the same."""
    with patch.dict("sys.modules", {"openai": _mock_openai_module()}):
        config = TranslationConfig(
            provider="OpenAI",
            model_default="gpt-4o",
            fallback_provider="openai",
        )
        adapter = create_translator(config)
    # No wrapping — primary == fallback after lower-case normalization.
    assert type(adapter).__name__ == "OpenAIAdapter"


# ── S5U-746 — Fallback metadata still recorded ───────────────────────


def test_factory_fallback_records_attempts_and_fallback_used() -> None:
    """``FallbackTranslator`` from the new factory still enriches metadata.

    Regression-pin on the success criterion "Fallback wrapping still records
    fallback_used and attempts metadata." We verify the wrapper is wired up
    correctly by calling it through with mocked adapters.
    """
    from atr_pipeline.services.llm.base import (
        TranslationResponse,
        TranslationResponseMeta,
    )
    from atr_schemas.translation_batch_v1 import TranslationBatchV1
    from atr_schemas.translation_result_v1 import TranslationResultV1

    with patch.dict(
        "sys.modules",
        {"openai": _mock_openai_module(), "anthropic": _mock_anthropic_module()},
    ):
        config = TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="anthropic",
            fallback_model="claude-sonnet-4-6",
            max_retries=0,
            retry_delay_seconds=0.0,
        )
        adapter = create_translator(config)

    # Replace the wrapped primary/fallback with mocks so we can drive the wrapper
    # without making an LLM call.
    primary_mock = MagicMock()
    primary_mock.translate_batch.return_value = TranslationResponse(
        result=TranslationResultV1(batch_id="b1"),
        meta=TranslationResponseMeta(provider="openai", model="gpt-4o"),
    )
    adapter._primary = primary_mock  # type: ignore[attr-defined]

    response = adapter.translate_batch(TranslationBatchV1(batch_id="b1"))
    assert response.meta.extra["fallback_used"] is False
    assert response.meta.extra["attempts"] == 1

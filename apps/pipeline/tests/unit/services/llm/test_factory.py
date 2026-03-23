"""Tests for translator factory provider selection and error paths."""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.config.models import TranslationConfig
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
    config = TranslationConfig(provider="nonexistent", fallback_provider="")
    with pytest.raises(ValueError, match="Unknown translation provider"):
        create_translator(config)


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

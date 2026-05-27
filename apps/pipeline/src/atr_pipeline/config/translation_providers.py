"""Translation provider validation helpers for config loading."""

from __future__ import annotations

KNOWN_TRANSLATION_PROVIDERS: frozenset[str] = frozenset(
    {"mock", "openai", "anthropic", "gemini", "gemini-cli", "codex-cli", "agy-cli"},
)

PROVIDERS_WITH_DEFAULT_MODEL: frozenset[str] = frozenset({"gemini", "gemini-cli"})
PROVIDERS_WITHOUT_MODEL: frozenset[str] = frozenset({"mock"})


def translation_provider_requires_model(provider: str) -> bool:
    """Return true when config must provide an explicit model for provider."""
    return (
        bool(provider)
        and provider not in PROVIDERS_WITHOUT_MODEL
        and provider not in PROVIDERS_WITH_DEFAULT_MODEL
    )


def validate_translation_provider_name(field_name: str, provider: str) -> None:
    """Reject unknown provider names before any LLM or subprocess call."""
    if not provider or provider in KNOWN_TRANSLATION_PROVIDERS:
        return
    msg = (
        f"Unknown translation {field_name}: {provider!r}. "
        f"Known providers: {sorted(KNOWN_TRANSLATION_PROVIDERS)}"
    )
    raise ValueError(msg)

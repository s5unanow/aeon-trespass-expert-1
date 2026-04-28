"""Factory-side tests for the Codex CLI adapter (S5U-747).

These tests pin (a) provider name acceptance, (b) option-threading from
``provider_options.cli`` into the adapter constructor, and (c) the
recommended primary/fallback pairing (``codex-cli`` + ``gemini-cli``).
Adapter-level argv/parse tests live in ``test_codex_cli_adapter.py`` /
``test_codex_cli_argv.py``.

Red-before anchor: on commit ``afacd3d`` (S5U-746 merge SHA, parent of
this branch), ``factory.py`` had ``_RESERVED_PROVIDERS = {"codex-cli"}``
and ``test_factory_rejects_codex_cli_until_adapter_lands`` asserted the
factory raises ``ValueError`` containing "S5U-747". Every test here would
fail with that assertion — the new factory code accepts ``codex-cli``
and returns a ``CodexCLIAdapter``. Resolve via
``git cat-file -e afacd3d^{commit}``.
"""

from __future__ import annotations

import pytest

from atr_pipeline.config.models import (
    CLIProviderOptions,
    TranslationConfig,
    TranslationProviderOptions,
)
from atr_pipeline.services.llm.factory import create_translator


def test_factory_creates_codex_cli_adapter() -> None:
    """Factory should instantiate CodexCLIAdapter for provider='codex-cli'."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
    )
    adapter = create_translator(config)
    assert type(adapter).__name__ == "CodexCLIAdapter"
    assert adapter._model == "gpt-5.5"  # type: ignore[attr-defined]


def test_factory_codex_cli_case_insensitive() -> None:
    """Casing variants (Codex-CLI, CODEX-CLI) all map to the canonical name."""
    for raw in ("Codex-CLI", "CODEX-CLI", "codex-CLI"):
        config = TranslationConfig(
            provider=raw,
            model_default="gpt-5.5",
            fallback_provider="",
        )
        adapter = create_translator(config)
        assert type(adapter).__name__ == "CodexCLIAdapter"


def test_factory_threads_cli_timeout_to_codex_cli() -> None:
    """``provider_options.cli.timeout_seconds`` is forwarded to CodexCLIAdapter."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(timeout_seconds=900),
        ),
    )
    adapter = create_translator(config)
    assert adapter._timeout == 900  # type: ignore[attr-defined]


def test_factory_threads_reasoning_effort_to_codex_cli() -> None:
    """``provider_options.cli.reasoning_effort`` is forwarded."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(reasoning_effort="xhigh"),
        ),
    )
    adapter = create_translator(config)
    assert adapter._reasoning_effort == "xhigh"  # type: ignore[attr-defined]


def test_factory_threads_sandbox_to_codex_cli() -> None:
    """``provider_options.cli.sandbox`` is forwarded."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(sandbox="workspace-write"),
        ),
    )
    adapter = create_translator(config)
    assert adapter._sandbox == "workspace-write"  # type: ignore[attr-defined]


def test_factory_threads_approval_policy_to_codex_cli() -> None:
    """``provider_options.cli.approval_policy`` is forwarded.

    Only ``never`` is allowed for non-interactive pipeline use; other
    values raise at adapter construction time (separately covered by
    ``test_factory_rejects_non_never_approval_policy_on_codex_cli``).
    """
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(approval_policy="never"),
        ),
    )
    adapter = create_translator(config)
    assert adapter._approval_policy == "never"  # type: ignore[attr-defined]


def test_factory_codex_cli_with_gemini_cli_fallback() -> None:
    """Codex CLI primary + Gemini CLI fallback wraps in FallbackTranslator.

    This is the canonical recommended deployment shape per the S5U-747
    success criterion: codex-cli primary, gemini-cli fallback.
    """
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="gemini-cli",
        fallback_model="gemini-2.5-flash",
    )
    adapter = create_translator(config)
    assert type(adapter).__name__ == "FallbackTranslator"
    assert type(adapter._primary).__name__ == "CodexCLIAdapter"  # type: ignore[attr-defined]
    assert type(adapter._fallback).__name__ == "GeminiCLIAdapter"  # type: ignore[attr-defined]


def test_factory_rejects_invalid_codex_cli_sandbox() -> None:
    """Adapter constructor refuses sandbox values outside the documented set."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(sandbox="full-trust"),  # not in upstream allowlist
        ),
    )
    with pytest.raises(ValueError, match="sandbox"):
        create_translator(config)


def test_factory_rejects_non_never_approval_policy_on_codex_cli() -> None:
    """Approval policies other than ``never`` are unsafe for non-interactive use."""
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(approval_policy="on-request"),
        ),
    )
    with pytest.raises(ValueError, match="approval_policy"):
        create_translator(config)

"""Pydantic-level validation tests for ``TranslationConfig`` (S5U-746).

These tests cover the config layer's role as the rejection boundary for
unknown providers, casing differences, missing required models, and
invalid timeouts/retries. Cross-provider option leakage is *factory*-level
and is covered in ``tests/unit/services/llm/test_factory.py``.
"""

from __future__ import annotations

import pytest

from atr_pipeline.config.models import (
    APIProviderOptions,
    CLIProviderOptions,
    DocumentBuildConfig,
    DocumentConfig,
    TranslationConfig,
    TranslationProviderOptions,
)

# ── Provider name normalization ──────────────────────────────────────


def test_translation_config_normalizes_provider_casing() -> None:
    """Mixed-case provider names are lower-cased so casing is a non-issue."""
    cfg = TranslationConfig(
        provider="Gemini-CLI",
        model_default="gemini-2.5-flash",
        fallback_provider="GEMINI",
        fallback_model="gemini-2.5-flash",
    )
    assert cfg.provider == "gemini-cli"
    assert cfg.fallback_provider == "gemini"


def test_translation_config_normalizes_codex_cli_casing() -> None:
    """``Codex-CLI`` and ``CODEX-CLI`` both map to the canonical name."""
    for raw in ("Codex-CLI", "CODEX-CLI", "codex-CLI"):
        cfg = TranslationConfig(
            provider=raw,
            model_default="codex-1",
            fallback_provider="",
        )
        assert cfg.provider == "codex-cli"


def test_translation_config_normalizes_agy_cli_casing() -> None:
    """``AGY-CLI`` maps to the canonical provider name."""
    cfg = TranslationConfig(
        provider="AGY-CLI",
        model_default="gemini-3-pro",
        fallback_provider="",
    )
    assert cfg.provider == "agy-cli"


# ── Unknown provider rejection ───────────────────────────────────────


def test_translation_config_rejects_unknown_provider() -> None:
    """Unknown provider names are rejected before any factory call."""
    with pytest.raises(ValueError, match="Unknown translation provider"):
        TranslationConfig(provider="claude-2", fallback_provider="")


def test_translation_config_rejects_unknown_fallback_provider() -> None:
    """Unknown fallback providers are rejected the same way."""
    with pytest.raises(ValueError, match="Unknown translation fallback_provider"):
        TranslationConfig(
            provider="openai",
            model_default="gpt-4o",
            fallback_provider="claude-2",
            fallback_model="claude-x",
        )


# ── Reserved provider name (codex-cli) ───────────────────────────────


def test_translation_config_accepts_codex_cli_at_config_layer() -> None:
    """``codex-cli`` is a reserved name accepted by config (factory rejects).

    This lets configs be authored against S5U-746 ahead of S5U-747's adapter
    landing. The factory still refuses to *instantiate* a codex-cli adapter,
    which is the actual runtime gate.
    """
    cfg = TranslationConfig(
        provider="codex-cli",
        model_default="codex-1",
        fallback_provider="",
    )
    assert cfg.provider == "codex-cli"


# ── Missing model_default for non-mock, non-Gemini providers ─────────


def test_translation_config_rejects_missing_model_for_openai() -> None:
    """OpenAI has no documented default model — empty model_default rejected."""
    with pytest.raises(ValueError, match="model_default"):
        TranslationConfig(
            provider="openai",
            model_default="",
            fallback_provider="",
        )


def test_translation_config_rejects_missing_model_for_anthropic() -> None:
    """Anthropic has no documented default model — empty rejected."""
    with pytest.raises(ValueError, match="model_default"):
        TranslationConfig(
            provider="anthropic",
            model_default="",
            fallback_provider="",
        )


def test_translation_config_allows_empty_model_for_gemini() -> None:
    """Gemini has a documented default — empty model_default allowed."""
    cfg = TranslationConfig(
        provider="gemini",
        model_default="",
        fallback_provider="",
    )
    assert cfg.model_default == ""  # adapter will fall back to gemini-2.5-flash


def test_translation_config_allows_empty_model_for_gemini_cli() -> None:
    """Gemini CLI has a documented default — empty model_default allowed."""
    cfg = TranslationConfig(
        provider="gemini-cli",
        model_default="",
        fallback_provider="",
    )
    assert cfg.model_default == ""


def test_translation_config_allows_empty_model_for_mock() -> None:
    """Mock has no model — empty model_default allowed."""
    cfg = TranslationConfig(
        provider="mock",
        model_default="",
        fallback_provider="",
    )
    assert cfg.provider == "mock"


def test_translation_config_rejects_missing_fallback_model_for_openai() -> None:
    """Fallback OpenAI without fallback_model is rejected the same way."""
    with pytest.raises(ValueError, match="fallback_model"):
        TranslationConfig(
            provider="gemini-cli",
            model_default="gemini-2.5-flash",
            fallback_provider="openai",
            fallback_model="",
        )


# ── Invalid numeric values ───────────────────────────────────────────


def test_translation_config_rejects_negative_max_retries() -> None:
    """``max_retries`` is constrained to non-negative integers."""
    with pytest.raises(ValueError):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            max_retries=-1,
        )


def test_translation_config_rejects_negative_retry_delay() -> None:
    """``retry_delay_seconds`` is constrained to non-negative floats."""
    with pytest.raises(ValueError):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            retry_delay_seconds=-0.5,
        )


def test_translation_config_rejects_negative_temperature() -> None:
    """``temperature`` must be between 0 and 2."""
    with pytest.raises(ValueError):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            temperature=-0.1,
        )


def test_translation_config_rejects_excessive_temperature() -> None:
    """``temperature`` greater than 2 is rejected."""
    with pytest.raises(ValueError):
        TranslationConfig(
            provider="mock",
            fallback_provider="",
            temperature=2.5,
        )


# ── Provider options namespacing ─────────────────────────────────────


def test_translation_provider_options_default_is_empty_namespaces() -> None:
    """Default ``TranslationProviderOptions`` has empty CLI + API namespaces."""
    opts = TranslationProviderOptions()
    assert opts.cli == CLIProviderOptions()
    assert opts.api == APIProviderOptions()


def test_cli_provider_options_rejects_negative_timeout() -> None:
    """CLI ``timeout_seconds`` is constrained to ``ge=1``."""
    with pytest.raises(ValueError):
        CLIProviderOptions(timeout_seconds=-1)


def test_cli_provider_options_rejects_zero_timeout() -> None:
    """CLI ``timeout_seconds`` of 0 is rejected (would never fire)."""
    with pytest.raises(ValueError):
        CLIProviderOptions(timeout_seconds=0)


def test_cli_provider_options_rejects_unknown_field() -> None:
    """CLI options use ``extra='forbid'`` so typos surface at load time."""
    with pytest.raises(ValueError):
        CLIProviderOptions(executible="/foo")  # typo of 'executable'  # type: ignore[call-arg]


def test_api_provider_options_rejects_unknown_field() -> None:
    """API options use ``extra='forbid'`` so typos surface at load time."""
    with pytest.raises(ValueError):
        APIProviderOptions(api_keey="x")  # type: ignore[call-arg]


def test_translation_config_accepts_nested_provider_options() -> None:
    """Nested ``[translation.provider_options.cli]`` config loads correctly."""
    cfg = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(timeout_seconds=600, json_mode=True),
        ),
    )
    assert cfg.provider_options.cli.timeout_seconds == 600
    assert cfg.provider_options.cli.json_mode is True


def test_translation_config_accepts_nested_fallback_options() -> None:
    """Fallback options are independently namespaced from primary."""
    cfg = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        fallback_provider="openai",
        fallback_model="gpt-4o",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(timeout_seconds=600),
        ),
        fallback_options=TranslationProviderOptions(
            api=APIProviderOptions(api_key="sk-test"),
        ),
    )
    assert cfg.provider_options.cli.timeout_seconds == 600
    assert cfg.fallback_options.api.api_key == "sk-test"


# ── Backward compatibility — flat-keys-only config ───────────────────


def test_translation_config_legacy_flat_keys_only() -> None:
    """A pre-S5U-746 flat-keys-only config still validates and gets defaults.

    The merged dict from ``configs/base.toml`` (no provider_options key)
    must validate and produce empty default options namespaces.
    """
    cfg = TranslationConfig(
        provider="gemini-cli",
        model_default="gemini-2.5-flash",
        model_hard="gemini-2.5-flash",
        fallback_provider="gemini",
        fallback_model="gemini-2.5-flash",
        temperature=0.0,
        batch_size=24,
        prompt_profile="translate_rules_ru.v1",
    )
    assert cfg.provider == "gemini-cli"
    assert cfg.provider_options == TranslationProviderOptions()
    assert cfg.fallback_options == TranslationProviderOptions()


def test_document_build_config_accepts_legacy_translation_block() -> None:
    """``DocumentBuildConfig.model_validate`` accepts a flat translation block.

    The historical schema deserialization path — used by the TOML loader
    (``load_document_config``) — must keep accepting configs that don't set
    the new nested options.
    """
    raw = {
        "document": {"id": "x", "source_pdf": "x.pdf"},
        "translation": {
            "provider": "gemini-cli",
            "model_default": "gemini-2.5-flash",
            "model_hard": "gemini-2.5-flash",
            "fallback_provider": "gemini",
            "fallback_model": "gemini-2.5-flash",
            "temperature": 0.0,
            "batch_size": 24,
            "prompt_profile": "translate_rules_ru.v1",
        },
    }
    cfg = DocumentBuildConfig.model_validate(raw)
    assert cfg.translation.provider == "gemini-cli"
    assert cfg.translation.provider_options.cli == CLIProviderOptions()


def test_document_build_config_accepts_nested_translation_options() -> None:
    """New nested options can be authored in a TOML-shaped dict."""
    raw = {
        "document": {"id": "x", "source_pdf": "x.pdf"},
        "translation": {
            "provider": "gemini-cli",
            "model_default": "gemini-2.5-flash",
            "fallback_provider": "",
            "provider_options": {
                "cli": {"timeout_seconds": 450, "json_mode": True},
            },
        },
    }
    cfg = DocumentBuildConfig.model_validate(raw)
    assert cfg.translation.provider_options.cli.timeout_seconds == 450


# ── DocumentConfig sanity (used by validate above) ───────────────────


def test_document_config_minimal_round_trip() -> None:
    """Minimal DocumentConfig — used as scaffolding by build-config tests."""
    doc = DocumentConfig(id="x", source_pdf="x.pdf")
    assert doc.id == "x"
    assert doc.source_lang == "en"


# ── S5U-747 — Recommended Codex CLI translation block validates ──────


def test_recommended_codex_cli_translation_block_validates() -> None:
    """The S5U-747 recommended ``[translation]`` block validates end-to-end.

    Pins the configs/base.toml + configs/documents/ato_core_v1_1.toml shape
    so a future TOML edit that drops a knob (or adds an unknown one) is
    caught at unit-test time rather than at first pipeline run.

    Red-before: this is a fixture/data extension on the existing
    ``DocumentBuildConfig.model_validate`` branch — same code path as
    the legacy block test, just pinned to the new authored values.
    Per ``.claude/rules/hooks.md`` § "Three-input test discipline" the
    extension carve-out applies; no new branch coverage.
    """
    raw = {
        "document": {"id": "ato_core_v1_1", "source_pdf": "x.pdf"},
        "translation": {
            "provider": "codex-cli",
            "model_default": "gpt-5.5",
            "model_hard": "gpt-5.5",
            "fallback_provider": "gemini-cli",
            "fallback_model": "gemini-2.5-flash",
            "temperature": 0.0,
            "batch_size": 24,
            "prompt_profile": "translate_rules_ru.v1",
            "provider_options": {
                "cli": {
                    "timeout_seconds": 600,
                    "json_mode": True,
                    "reasoning_effort": "xhigh",
                    "sandbox": "read-only",
                    "approval_policy": "never",
                },
            },
        },
    }
    cfg = DocumentBuildConfig.model_validate(raw)
    assert cfg.translation.provider == "codex-cli"
    assert cfg.translation.fallback_provider == "gemini-cli"
    assert cfg.translation.provider_options.cli.reasoning_effort == "xhigh"
    assert cfg.translation.provider_options.cli.sandbox == "read-only"
    assert cfg.translation.provider_options.cli.approval_policy == "never"
    assert cfg.translation.provider_options.cli.timeout_seconds == 600


# fmt: off
def test_translation_config_accepts_hardness_section() -> None:
    raw={"document":{"id":"x","source_pdf":"x.pdf"},"translation":{"provider":"mock","model_default":"def","model_hard":"hard","hardness":{"enabled":True,"threshold":0.65}}}
    assert DocumentBuildConfig.model_validate(raw).translation.hardness.enabled
def test_translation_config_hardness_rejects_unknown_keys() -> None:
    raw={"document":{"id":"x","source_pdf":"x.pdf"},"translation":{"provider":"mock","model_default":"def","hardness":{"enabled":True,"junk":1}}}
    with pytest.raises(ValueError):
        DocumentBuildConfig.model_validate(raw)
# fmt: on

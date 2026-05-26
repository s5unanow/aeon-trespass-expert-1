"""Build a TranslatorAdapter from pipeline configuration."""

from __future__ import annotations

from atr_pipeline.config.models import (
    APIProviderOptions,
    CLIProviderOptions,
    TranslationConfig,
    TranslationProviderOptions,
)
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_schemas.concept_registry_v1 import ConceptRegistryV1

# Provider shape — which options namespace is *legitimate* for each provider.
# Cross-namespace options (e.g. CLI options on an API provider) are rejected
# at factory time when set to non-default values, so a config bug surfaces
# before any LLM/subprocess call (S5U-746 "must refuse" — option leakage).
_CLI_PROVIDERS: frozenset[str] = frozenset({"gemini-cli", "codex-cli", "agy-cli"})
_API_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "gemini"})
_NO_OPTIONS_PROVIDERS: frozenset[str] = frozenset({"mock"})

# No reserved-but-unimplemented providers as of S5U-747. The slot remains
# (typed) so adding a future reserved name is a one-line change.
_RESERVED_PROVIDERS: frozenset[str] = frozenset()


def _cli_options_are_default(opts: CLIProviderOptions) -> bool:
    """Return True if *opts* equals ``CLIProviderOptions()`` (no leakage)."""
    return opts == CLIProviderOptions()


def _api_options_are_default(opts: APIProviderOptions) -> bool:
    """Return True if *opts* equals ``APIProviderOptions()`` (no leakage)."""
    return opts == APIProviderOptions()


def _check_options_match_provider(
    provider: str,
    options: TranslationProviderOptions,
    *,
    label: str,
) -> None:
    """Reject cross-provider option leakage with a clear error.

    *label* is ``"primary"`` or ``"fallback"`` and used in the error message.
    Default-empty option namespaces are always accepted (they are the Pydantic
    default and don't reflect a worker setting); only *non-default* values
    that don't match the provider's shape are rejected.
    """
    if provider in _NO_OPTIONS_PROVIDERS:
        if not _cli_options_are_default(options.cli) or not _api_options_are_default(
            options.api,
        ):
            msg = (
                f"{label} provider {provider!r} accepts no provider options, "
                f"but provider_options.cli or provider_options.api is set."
            )
            raise ValueError(msg)
        return

    if provider in _CLI_PROVIDERS:
        # CLI options are accepted; non-default API options are leakage.
        if not _api_options_are_default(options.api):
            msg = (
                f"{label} provider {provider!r} is a CLI provider but "
                f"provider_options.api is set; API options apply only to "
                f"'openai', 'anthropic', and 'gemini'."
            )
            raise ValueError(msg)
        return

    if provider in _API_PROVIDERS:
        # API options are accepted; non-default CLI options are leakage.
        if not _cli_options_are_default(options.cli):
            msg = (
                f"{label} provider {provider!r} is an API provider but "
                f"provider_options.cli is set; CLI options apply only to "
                f"'gemini-cli' and 'codex-cli'."
            )
            raise ValueError(msg)
        return

    # Unknown provider — the config validator should have caught this; if we
    # reach here something has bypassed Pydantic. Fail closed.
    msg = f"Unknown {label} translation provider: {provider!r}"
    raise ValueError(msg)


def _create_codex_cli_adapter(
    model: str,
    options: TranslationProviderOptions,
    concept_registry: ConceptRegistryV1 | None,
) -> TranslatorAdapter:
    from atr_pipeline.services.llm.codex_cli_adapter import CodexCLIAdapter

    cli_opts = options.cli
    kwargs: dict[str, object] = {
        "model": model,
        "concept_registry": concept_registry,
        "timeout_seconds": cli_opts.timeout_seconds,
    }
    # Only forward CLI-specific knobs when explicitly set, so the
    # adapter's documented defaults remain authoritative when the
    # config doesn't override them. ``None`` is the "not set" sentinel
    # for these fields on ``CLIProviderOptions``.
    if cli_opts.reasoning_effort is not None:
        kwargs["reasoning_effort"] = cli_opts.reasoning_effort
    if cli_opts.sandbox is not None:
        kwargs["sandbox"] = cli_opts.sandbox
    if cli_opts.approval_policy is not None:
        kwargs["approval_policy"] = cli_opts.approval_policy
    if cli_opts.executable is not None:
        kwargs["executable"] = cli_opts.executable
    kwargs["json_events"] = cli_opts.json_mode
    return CodexCLIAdapter(**kwargs)  # type: ignore[arg-type]


def _create_agy_cli_adapter(
    model: str,
    options: TranslationProviderOptions,
    concept_registry: ConceptRegistryV1 | None,
) -> TranslatorAdapter:
    from atr_pipeline.services.llm.agy_cli_adapter import AgyCLIAdapter

    cli_opts = options.cli
    default_cli = CLIProviderOptions()
    unsupported: list[str] = []
    if cli_opts.sandbox != default_cli.sandbox:
        unsupported.append("sandbox")
    if cli_opts.approval_policy != default_cli.approval_policy:
        unsupported.append("approval_policy")
    if cli_opts.json_mode != default_cli.json_mode:
        unsupported.append("json_mode")
    if cli_opts.output_file_mode != default_cli.output_file_mode:
        unsupported.append("output_file_mode")
    if unsupported:
        msg = (
            "agy-cli does not support these CLI options in non-interactive "
            f"mode: {', '.join(unsupported)}"
        )
        raise ValueError(msg)

    kwargs: dict[str, object] = {
        "model": model,
        "concept_registry": concept_registry,
        "timeout_seconds": cli_opts.timeout_seconds,
    }
    if cli_opts.reasoning_effort is not None:
        kwargs["reasoning_effort"] = cli_opts.reasoning_effort
    if cli_opts.executable is not None:
        kwargs["executable"] = cli_opts.executable
    return AgyCLIAdapter(**kwargs)  # type: ignore[arg-type]


def _create_single_adapter(
    provider: str,
    model: str,
    temperature: float,
    options: TranslationProviderOptions,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslatorAdapter:
    """Instantiate a single adapter for the given *provider* name.

    *provider* is expected to already be lower-cased by ``TranslationConfig``'s
    validator; we lower-case again defensively in case a caller bypasses the
    config layer.
    """
    provider = provider.lower()

    if provider in _RESERVED_PROVIDERS:
        msg = (
            f"Translation provider {provider!r} is reserved but its adapter "
            f"is not yet implemented (tracked under S5U-747). Use "
            f"'gemini-cli' until that lands."
        )
        raise ValueError(msg)

    if provider == "mock":
        from atr_pipeline.services.llm.mock_translator import MockTranslator

        return MockTranslator()

    if provider == "openai":
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            api_key=options.api.api_key,
            model=model,
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "anthropic":
        from atr_pipeline.services.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            api_key=options.api.api_key,
            model=model,
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "gemini":
        from atr_pipeline.services.llm.gemini_adapter import GeminiAdapter

        return GeminiAdapter(
            api_key=options.api.api_key,
            model=model or "gemini-2.5-flash",
            temperature=temperature,
            concept_registry=concept_registry,
        )

    if provider == "gemini-cli":
        from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

        return GeminiCLIAdapter(
            model=model or "gemini-2.5-flash",
            concept_registry=concept_registry,
            timeout_seconds=options.cli.timeout_seconds,
        )

    if provider == "codex-cli":
        return _create_codex_cli_adapter(model, options, concept_registry)

    if provider == "agy-cli":
        return _create_agy_cli_adapter(model, options, concept_registry)

    msg = f"Unknown translation provider: {provider!r}"
    raise ValueError(msg)


def create_translator(
    config: TranslationConfig,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> TranslatorAdapter:
    """Instantiate the adapter specified by *config.provider*.

    When a ``fallback_provider`` is configured (and differs from the primary
    after lower-case normalization), the returned adapter is a
    :class:`FallbackTranslator` that retries the primary then falls back.
    Mock providers skip fallback wrapping to keep test output deterministic.

    Provider-specific options are taken from ``config.provider_options`` for
    the primary and ``config.fallback_options`` for the fallback. Cross-
    provider option leakage (CLI options on an API provider, or vice-versa)
    is rejected with a clear error before any adapter is constructed.
    """
    primary_provider = config.provider.lower()
    _check_options_match_provider(
        primary_provider,
        config.provider_options,
        label="primary",
    )

    primary = _create_single_adapter(
        primary_provider,
        config.model_default,
        config.temperature,
        config.provider_options,
        concept_registry,
    )

    fallback_provider = (config.fallback_provider or "").lower()
    use_fallback = (
        bool(fallback_provider)
        and fallback_provider != primary_provider
        and primary_provider != "mock"
    )

    if not use_fallback:
        return primary

    _check_options_match_provider(
        fallback_provider,
        config.fallback_options,
        label="fallback",
    )

    from atr_pipeline.services.llm.fallback import FallbackTranslator

    try:
        fallback = _create_single_adapter(
            fallback_provider,
            config.fallback_model,
            config.temperature,
            config.fallback_options,
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

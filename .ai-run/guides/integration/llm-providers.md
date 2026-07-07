# LLM Provider Integration

**Purpose**: translation-stage LLM provider selection and fallback. Full operational doc: `docs/specs/translation-providers.md`.

---

## Supported Providers

Seven providers (`docs/specs/translation-providers.md:6-7`): `mock`, `openai`, `anthropic`, `gemini`, `gemini-cli`, `codex-cli`, `agy-cli`. Only the CLI providers (`gemini-cli`, `codex-cli`) are used for production translation runs — the API providers (`openai`, `anthropic`, `gemini`) are optional dependencies (`apps/pipeline/pyproject.toml:15-19`), not the default path.

---

## Recommended Deployment Shape

`codex-cli` primary + `gemini-cli` fallback (local-subscription-priced, no per-token billing), pinned by the factory test `test_factory_codex_cli_with_gemini_cli_fallback` (`docs/specs/translation-providers.md:9-12`).

```toml
[translation]
provider = "codex-cli"
model_default = "gpt-5.5"
fallback_provider = "gemini-cli"
fallback_model = "gemini-2.5-flash"
```

Config lives per-document at `configs/documents/<doc-id>.toml`.

---

## Known Constraints

- Codex `/fast` mode and `codex exec` both hang when invoked non-interactively/headlessly — a cross-system-review issue that touches translation cannot ship fully autonomously via the CLI provider path (see `docs/specs/translation-providers.md` for the opt-in `ATR_CODEX_LIVE_SMOKE=1` smoke test that verifies live-CLI behavior).
- Provider switching is config-only (no code change) — see `docs/specs/translation-providers.md` for the full provider-option matrix per CLI provider.

---

## Quick Reference

| Need | Location |
|------|----------|
| Full provider-switching doc | `docs/specs/translation-providers.md` |
| Optional LLM deps | `apps/pipeline/pyproject.toml` `[project.optional-dependencies.llm]` |
| Per-document provider config | `configs/documents/<doc-id>.toml` |

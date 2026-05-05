# Translation providers — switching between gemini-cli and codex-cli

This document covers the operational surface for translation provider
selection: switching the configured primary, the recommended deployment
shape, and the opt-in Codex CLI smoke command. The pipeline supports
six providers today: `mock`, `openai`, `anthropic`, `gemini`,
`gemini-cli`, `codex-cli`. The two CLI providers are the only ones used
for production translation runs.

## Recommended deployment shape (S5U-747)

`codex-cli` (primary) + `gemini-cli` (fallback). The factory test
`test_factory_codex_cli_with_gemini_cli_fallback` pins this pairing.
Both options are local-subscription-priced (no per-token API billing).

## Switching primary provider

Edit the `[translation]` block in your document config (e.g.
`configs/documents/<doc-id>.toml` or the pipeline-level config you load):

### codex-cli primary (recommended)

```toml
[translation]
provider = "codex-cli"
model_default = "gpt-5.5"
fallback_provider = "gemini-cli"
fallback_model = "gemini-2.5-flash"

[translation.provider_options.cli]
reasoning_effort = "xhigh"
sandbox = "read-only"
approval_policy = "never"
timeout_seconds = 900
```

### gemini-cli primary (fallback shape)

```toml
[translation]
provider = "gemini-cli"
model_default = "gemini-2.5-flash"
fallback_provider = "gemini"
fallback_model = "gemini-2.5-flash"

[translation.provider_options.cli]
timeout_seconds = 300
```

Field semantics:

* `provider` and `fallback_provider` accept the canonical names listed
  above; case is normalized lower-case at config load.
* `provider_options.cli` carries CLI-specific knobs (timeout, reasoning
  effort, sandbox mode, approval policy). Cross-namespace leakage —
  e.g. CLI options on an API provider — is rejected at factory time.
* The `approval_policy` allowlist is `{"never"}` only; any other value
  is interactive and unsafe for unattended pipeline runs.
* The `sandbox` allowlist mirrors the upstream `[possible values:
  read-only, workspace-write, danger-full-access]` set.
* `--dangerously-bypass-approvals-and-sandbox` is **never** emitted by
  the adapter (pinned by `test_codex_cli_argv_never_uses_dangerous_bypass`).

## Codex CLI smoke command

The pipeline ships an opt-in smoke test that translates one fixture page
end-to-end via a real `codex` subprocess. It is excluded from default
`pytest` and the pre-commit hook. To run it:

```bash
ATR_CODEX_LIVE_SMOKE=1 uv run pytest -m codex_live \
    apps/pipeline/tests/unit/services/llm/test_codex_cli_smoke.py -v
```

Both gates are required:

1. `-m codex_live` selects the marker so pytest collects the test.
2. `ATR_CODEX_LIVE_SMOKE=1` is the env-var double-gate inside the test
   body — without it, the test skips immediately even if the marker is
   selected.

Prerequisites:

* `codex` is installed and on PATH (`codex --version` should return 0).
* The OpenAI account behind your `codex` install has access to
  `gpt-5.5`.
* A network connection to the Codex CLI's upstream service.

The smoke test uses the walking-skeleton fixture page
(`packages/fixtures/sample_documents/walking_skeleton/expected/translation_batch.p0001.json`),
which is one heading + one paragraph — small enough to translate cheaply
and verify the wiring without burning the full 83-page rulebook budget.

The captured response is written to
`tmp/smoke-s5u-748-<timestamp>.json` (`tmp/` is gitignored). The smoke
test never writes to `packages/fixtures/`, never writes to
`artifacts/`, and never points at more than one fixture page.

## CI determinism

* Default `make test` and CI's `pytest --tb=short` collect the smoke
  test but it `pytest.skip`s on the env-var check before any subprocess
  call — no `codex` subprocess is invoked, no Codex auth is required,
  no paid call happens.
* Every other test in `tests/unit/services/llm/` mocks `subprocess.run`
  at the module boundary; no test outside `test_codex_cli_smoke.py`
  shells out to a real `codex` or `gemini` binary.
* Provider conformance tests in `test_provider_conformance.py` exercise
  the full grid (mock, gemini-cli, codex-cli) with all external
  surfaces mocked — they ride the default `pytest` invocation and
  guarantee provider-switching stays safe.

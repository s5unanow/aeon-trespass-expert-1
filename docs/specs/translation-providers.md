# Translation providers — switching between gemini-cli and codex-cli

This document covers the operational surface for translation provider
selection: switching the configured primary, the recommended deployment
shape, and the opt-in Codex CLI smoke command. The pipeline supports
seven providers today: `mock`, `openai`, `anthropic`, `gemini`,
`gemini-cli`, `codex-cli`, `agy-cli`. The CLI providers are the only ones
used for production translation runs.

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

### agy-cli primary (experimental)

```toml
[translation]
provider = "agy-cli"
model_default = "gemini-3-pro"
fallback_provider = "codex-cli"
fallback_model = "gpt-5.5"

[translation.provider_options.cli]
timeout_seconds = 900
reasoning_effort = "high"
```

`agy-cli` shells out to `agy --print-timeout <N>s --print <prompt>`. As of the local
AGY CLI v1 help surface, there is no non-interactive model/effort selector.
The adapter records the requested `model_default` / `reasoning_effort` in
metadata and embeds it in the prompt; the actual model profile must be selected
in the user's Antigravity CLI/session configuration until AGY exposes stable
flags.

Field semantics:

* `provider` and `fallback_provider` accept the canonical names listed
  above; case is normalized lower-case at config load.
* `provider_options.cli` carries CLI-specific knobs. For `agy-cli`, only
  `executable`, `timeout_seconds`, and `reasoning_effort` are accepted;
  `sandbox`, `approval_policy`, `json_mode=false`, and `output_file_mode=true`
  are rejected because AGY v1 exposes no matching non-interactive controls.
  `reasoning_effort` is a real Codex CLI config override and an AGY
  prompt/metadata hint. Cross-namespace leakage — e.g. CLI options on an API
  provider — is rejected at factory time.
* The `approval_policy` allowlist is `{"never"}` only; any other value
  is interactive and unsafe for unattended pipeline runs.
* The `sandbox` allowlist mirrors the upstream `[possible values:
  read-only, workspace-write, danger-full-access]` set.
* `--dangerously-bypass-approvals-and-sandbox` is **never** emitted by
  the adapter (pinned by `test_codex_cli_argv_never_uses_dangerous_bypass`).

## Hard-page routing (S5U-1542)

Icon-dense / xref-dense / table-heavy pages can be routed to `model_hard`
deterministically. The routing is **off by default** — existing configs are
byte-identical unless the `[translation.hardness]` section turns it on:

```toml
[translation]
provider = "codex-cli"
model_default = "gpt-5.5"
model_hard = "gpt-5.5-high"        # the model hard pages escalate to

[translation.hardness]
enabled = true
threshold = 2.0                    # score >= threshold routes to model_hard
weight_icon_density = 1.0          # inline icons per segment
weight_xref_density = 1.0          # real cross-references per segment
weight_table_ratio = 1.0          # fraction of segments that are table cells
weight_segment_load = 0.05        # segment count (page-size proxy)
```

Semantics:

* Each page's `TranslationBatchV1` is scored by a pure, deterministic linear
  model: `score = Σ weight_i * signal_i`. A page whose score is `>= threshold`
  is translated by `model_hard`; every other page keeps `model_default`.
  Narrative-group boundary markers are synthetic and excluded from the
  cross-reference count.
* Provider **fallback semantics are unchanged**: the hard path is a second
  translator whose primary uses `model_hard` while `fallback_provider` /
  `fallback_model` stay as configured — hard pages do **not** change what the
  fallback provider translates with.
* The score, per-signal feature/contribution breakdown, threshold, verdict,
  and chosen model are recorded in the per-page `translation_meta.v1` artifact
  under a `hardness` key (present only when the section is enabled), so a
  routing decision is reproducible and auditable across runs on identical
  inputs.
* All knobs are validated by Pydantic with `extra="forbid"`; an unknown key
  (e.g. a typo) fails config load rather than being silently ignored.

**Follow-up (out of scope here):** extraction-side confidence signals
(S5U-191 groundwork) are not yet part of the hardness score — the classifier
uses only signals derivable from the pre-translation `PageIRV1` / batch. Wiring
per-page extraction confidence into the score is tracked as future work.

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
  shells out to a real `codex`, `gemini`, or `agy` binary.
* Provider conformance tests in `test_provider_conformance.py` exercise
  the full grid (mock, gemini-cli, codex-cli, agy-cli) with all external
  surfaces mocked — they ride the default `pytest` invocation and
  guarantee provider-switching stays safe.

# Local model cache — pointer to Mac-wide layout

This file is the **project-side contract** with the Mac-wide local model
store. Authoritative layout, env vars, runtime decision tree, and
download / cleanup commands live in `~/Models/README.md` on the developer
workstation. That file is not project-specific; this one is.

## Layout (canonical, see `~/Models/README.md` for full rationale)

```
~/Models/
├── huggingface/        HF_HOME       — Transformers, MLX, sentence-transformers, llama.cpp
└── ollama/             OLLAMA_MODELS — Ollama daemon-managed manifests + blobs
```

Two env vars redirect every Python / CLI tool to this tree. Declare them in
your shell environment.

**This Mac (nix-darwin + home-manager via `~/dotfiles/`)** — add inside the
`home = { ... };` block in `~/dotfiles/home/default.nix` and apply with the
existing `rebuild` alias (`sudo darwin-rebuild switch --flake ~/dotfiles`):

```nix
home = {
  # ... existing username, homeDirectory, stateVersion, packages ...

  sessionVariables = {
    HF_HOME = "$HOME/Models/huggingface";
    OLLAMA_MODELS = "$HOME/Models/ollama";
  };
};
```

`home.sessionVariables` writes to home-manager's env-only file, so the vars
are available in non-interactive shells too (cron, launchd, IDE).

After `rebuild`, new terminal tabs may still show the old env because of the
`__HM_SESS_VARS_SOURCED` guard inherited from the parent terminal app —
fully quit the terminal app (Cmd+Q kitty) and reopen, or run `unset
__HM_SESS_VARS_SOURCED __HM_ZSH_SESS_VARS_SOURCED && exec zsh -l` in an
existing shell. See `~/Models/README.md` § "Gotcha: after editing
`home.sessionVariables`" for the full explanation.

**Non-Nix Macs** (fallback) — append to `~/.zshrc`:

```bash
export HF_HOME="$HOME/Models/huggingface"
export OLLAMA_MODELS="$HOME/Models/ollama"
```

See `~/Models/README.md` for verification commands and the full Nix-vs-bash
rationale.

## What this pipeline expects

* Local-model provider adapters (added per S5U-766 follow-ups) read
  `HF_HOME` and `OLLAMA_MODELS` from the environment. **Do not hardcode
  paths** in `apps/pipeline/`.
* Model weights are **never** committed to this repo and **never** written
  under `apps/pipeline/`, `packages/`, or `artifacts/`. Downloads always
  land in `~/Models/`.
* CI runs translation with `provider = "mock"` (overlay
  `configs/ci.toml`) — no local-model cache access in CI, no GitHub-runner
  storage of weights.

## Current provider state

No HF / MLX / Ollama provider exists in
`apps/pipeline/src/atr_pipeline/services/llm/` yet. The six providers in
the factory registry today (`mock`, `openai`, `anthropic`, `gemini`,
`gemini-cli`, `codex-cli`) either hit hosted APIs or shell out to external
CLIs that manage their own auth and cache; none read `HF_HOME` or
`OLLAMA_MODELS`. See `docs/specs/translation-providers.md` for operational
provider switching.

## Adding a new local-model provider (checklist for S5U-766 children)

1. Add adapter at
   `apps/pipeline/src/atr_pipeline/services/llm/<runtime>_adapter.py`,
   following the `GeminiCLIAdapter` / `CodexCLIAdapter` shape for
   subprocess providers (Ollama, llama-cpp CLI) or a direct-import shape
   for in-process providers (Transformers, MLX).
2. Wire the adapter into the factory registry in
   `apps/pipeline/src/atr_pipeline/services/llm/factory.py`.
3. Adapter resolves model paths via `os.environ["HF_HOME"]` /
   `os.environ["OLLAMA_MODELS"]`. Fail fast with a clear error if the env
   var is unset — do not fall back to defaults silently.
4. Document configuration knobs (model id, revision pin, quantization,
   etc.) in the `[translation]` block per the existing
   `docs/specs/translation-providers.md` convention.
5. Add a conformance test alongside `test_provider_conformance.py` that
   exercises the new provider with all external surfaces mocked.

## Cross-references

* `~/Models/README.md` — Mac-wide canonical layout doc (the source of
  truth this file points to).
* `docs/specs/translation-providers.md` — operational provider switching
  for the existing CLI providers.
* Linear epic `S5U-766` — parent (evaluate local open MT models for
  EN→RU).
* Linear issue `S5U-767` — this layout decision.
* Linear issue `S5U-772` — make the env-var setup Nix-aware on this Mac.
* Linear issue `S5U-773` — document the inherited-guard gotcha after `rebuild`.

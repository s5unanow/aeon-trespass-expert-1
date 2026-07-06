# Architecture Guide

**Project**: aeon-trespass-expert (`atr-pipeline` + `@atr/web`)
**Style**: Layered pipeline (staged IR compiler) + static SPA reader
**Language**: Python 3.12 / TypeScript · **Framework**: Typer + Pydantic / React 19 + Vite 6

IR-first document compiler that turns the Aeon Trespass rulebook PDF into immutable
intermediate-representation artifacts, translates EN→RU, runs release-blocking QA, and
emits a bundle a static React reader renders. Canonical decisions live in `docs/adrs/`.

## Architecture Overview

```
PDF ─► ingest ─► extract_native ─► extract_layout ─► symbols ─► structure
        ─► translation ─► render ─► qa ─► publish ─► site bundle ─► apps/web reader
```

**Key decision**: the IR (Pydantic models), not Markdown, is the canonical state —
`docs/adrs/ADR-001-ir-first-canonical-state.md`, `docs/adrs/ADR-002-markdown-not-source-of-truth.md`.
Artifacts are immutable and content-addressed; re-runs patch, never mutate —
`docs/adrs/ADR-003-immutable-artifacts-and-patches.md`.

## Component Structure

```
apps/pipeline/    Python compiler (uv, Typer CLI `atr`)
  src/atr_pipeline/
    cli/          Command entrypoints (atr_pipeline.cli.main:app)
    runner/       Stage executor, cache keys, run context
    stages/       Ordered pipeline stages (ingest…publish)
    services/     LLM adapters, PDF raster, asset store
    store/        Content-addressed + atomic artifact IO
    config/ registry/ eval/ utils/
apps/web/         React 19 / Vite static reader
packages/schemas/ Pydantic (python/) → jsonschema/ → ts/ (generated)
packages/fixtures/ Extraction fixtures
```

## Layer Responsibilities

The pipeline layering is machine-enforced by import-linter — `pyproject.toml:94`
(`[[tool.importlinter.contracts]]` "Pipeline layer contract").

| Layer | Responsibility | May import |
|---|---|---|
| `cli` | Command surface | runner, below |
| `runner` | Stage orchestration, executor, cache keys | stages/eval, below |
| `stages` \| `eval` | Individual compile stages / scoring | services, store, registry, below |
| `services` \| `store` \| `registry` | LLM/PDF/asset IO, artifact persistence | config, utils |
| `config` | Loaded TOML config | utils |
| `utils` | Leaf helpers | — |

Documented intentional cross-layer edges (e.g. `stages.* → runner.stage_context`) are
enumerated as `ignore_imports` at `pyproject.toml:117` — do not add new ones without
a comment justifying them there.

## Dependency Rules

| Rule | Enforced by |
|---|---|
| No upward or cyclic imports between pipeline layers | `lint-imports` (import-linter), `pyproject.toml:91` |
| No import cycles in web | oxlint `import/no-cycle: error`, `apps/web/.oxlintrc.json` |
| Stages read the runtime context but not orchestration logic | `ignore_imports` allowlist, `pyproject.toml:117` |

**Violations to avoid:**
- ❌ A stage importing `runner.executor` / `runner.registry` (only `runner.stage_context` is allowed).
- ❌ Adding a new cross-layer edge without a justifying comment in the `ignore_imports` block.

## Data Flow

A run threads an immutable IR through ordered stages; each stage's output is cached by a
key that includes the stage `version` — `apps/pipeline/src/atr_pipeline/runner/cache_keys.py:8`
(`build_cache_key`). A stage that adds a new artifact write MUST bump its `version` or
cached runs silently omit it (see `.claude/rules/pipeline.md`, S5U-662 retrospective).

**Example flow** (compile a page):
1. `ingest` registers the source PDF.
2. `extract_native` (PyMuPDF) + `extract_layout` (Docling) produce evidence.
3. `symbols` / `structure` recover blocks and iconography.
4. `translation` fills structured EN→RU contracts.
5. `render` builds page render; `qa` gates; `publish` writes the bundle.

## Key Abstractions

| Abstraction | Purpose | Location |
|---|---|---|
| `TranslatorAdapter` (Protocol) | Provider-agnostic translation contract | `apps/pipeline/src/atr_pipeline/services/llm/base.py:33` |
| `atomic_write_bytes` / `atomic_write_text` | Crash-safe artifact writes (temp + `os.replace`) | `apps/pipeline/src/atr_pipeline/store/atomic_write.py:11` |
| `build_cache_key` | Stage cache identity incl. `stage_v` | `apps/pipeline/src/atr_pipeline/runner/cache_keys.py:8` |
| Shared Pydantic schemas | Single contract source → JSONSchema → TS | `packages/schemas/python/` |

## Adding New Features

### To add a new pipeline stage:
1. Create `apps/pipeline/src/atr_pipeline/stages/<name>/stage.py` with a `version` field.
2. Persist outputs via `store` atomic/artifact writes only — never raw `Path.write_*`.
3. If you add a new artifact write to an existing stage, **bump its `version`** and add a
   cache-hit regression test (`.claude/rules/pipeline.md`).
4. Keep imports within the layer contract; justify any new `ignore_imports` edge.

### To add a new translation/LLM provider:
1. Implement `TranslatorAdapter` in `services/llm/<provider>_adapter.py`.
2. Wire it into `create_translator` — `services/llm/factory.py:232`.
3. Document the switch in `docs/specs/translation-providers.md`.

## Configuration & Environment

| Config type | Location | Accessed via |
|---|---|---|
| Documents / base / CI / glossary / symbols | `configs/*.toml` | `atr_pipeline.config` |
| Pipeline run data | `artifacts/` (gitignored) | `store` / `registry` |
| Secrets | never committed (hook secret-guard) | environment only |

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|---|---|
| Treat the IR as canonical; edit models, regenerate schemas | Hand-edit Markdown or generated `packages/schemas/ts/` |
| Write artifacts via `store` atomic helpers | Use plain `Path.write_text` / `write_bytes` for artifacts |
| Respect the import-layer contract | Introduce cross-layer or cyclic imports |
| Bump stage `version` when adding a side-effect | Add an artifact write with an unchanged `version` |

## Quick Reference

| Need | Location |
|---|---|
| CLI entry | `apps/pipeline/src/atr_pipeline/cli/main.py` (`atr`) |
| Stage orchestration | `apps/pipeline/src/atr_pipeline/runner/` |
| Pipeline stages | `apps/pipeline/src/atr_pipeline/stages/` |
| Artifact IO | `apps/pipeline/src/atr_pipeline/store/` |
| Web reader | `apps/web/src/` (`App.tsx`, `router.tsx`) |
| Schemas (source of truth) | `packages/schemas/python/` |
| Architecture decisions | `docs/adrs/ADR-001..013` |

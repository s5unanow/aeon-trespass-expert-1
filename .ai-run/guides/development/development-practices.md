# Development Practices

Conventions that span both apps. Language-specific deep rules are path-triggered in `.claude/rules/{pipeline,web,schemas}.md`; this guide is the cross-cutting summary. Exact lint/format/test commands are in `quality-gates.md`.

## Python (`apps/pipeline`, `packages/schemas`)

**Linter/formatter**: ruff (`pyproject.toml` `[tool.ruff]`, line-length 100, McCabe C901 max 12). **Types**: mypy `--strict`. **Imports**: import-linter layered contract (`pyproject.toml:91`).

### Error handling

| ✅ DO | ❌ DON'T |
|---|---|
| Record failures as structured events with context — stage `run()` errors become a `failed` event (`apps/pipeline/src/atr_pipeline/runner/executor.py:125`) | Add a bare `except Exception` with no logging (NEVER-list item) |
| Fail loud on unexpected state | Swallow errors with `except: pass` (S5U-1234 removed these) |

### Logging

Stdlib `logging.getLogger(__name__)` at module scope is the current default across the pipeline (e.g. `apps/pipeline/src/atr_pipeline/services/llm/anthropic_adapter.py:19`). Prefer `structlog` only for *new* services needing structured fields; do not migrate existing code. Never use `print()` for diagnostics. Detail: `.claude/rules/pipeline.md`.

### Artifact writes are atomic

All artifact output goes through `atomic_write_bytes` / `atomic_write_text` (temp file + fsync + `os.replace`) — `apps/pipeline/src/atr_pipeline/store/atomic_write.py:11`. `put_json` content-addresses and dedupes (`apps/pipeline/src/atr_pipeline/store/artifact_store.py:45`).

| ✅ DO | ❌ DON'T |
|---|---|
| Write artifacts via `atomic_write_*` / the artifact store | Use plain `Path.write_text`/`write_bytes` for artifacts |
| Bump a stage's `version` when adding a new write | Add a side-effect with an unchanged version (silent cache miss) |

### Import layers

Enforced order (top imports lower, never the reverse): `cli > runner > stages|eval > services|store|registry > config > utils` (`pyproject.toml:94`). Intentional exceptions are in a reviewer-visible `ignore_imports` allowlist (`pyproject.toml:116`). No cyclic dependencies.

### File length

Max 400 lines per source and test file (`scripts/check_file_length.py`); pre-existing violators are grandfathered and must not grow.

## TypeScript (`apps/web`)

**Linter**: oxlint (`apps/web/.oxlintrc.json`) with `import/no-cycle: error` (`:12`) and `eslint/max-lines: {max: 400}` (`:13`). **Types**: `tsc --noEmit`.

| ✅ DO | ❌ DON'T |
|---|---|
| Import shared types from `@atr/schemas` — e.g. `apps/web/src/lib/render/types.ts:22` | Hand-write TypeScript types (generate from Pydantic — see `architecture/schemas-codegen.md`) |
| Keep components single-responsibility; use an exhaustive `switch`/`never` for schema kinds (`apps/web/src/components/reader/BlockRenderer.tsx:16`) | Let a file grow past 400 lines or introduce import cycles |
| Style via CSS custom-property tokens (`apps/web/src/styles/tokens.css:1`) | Scatter hard-coded colors/spacing |

## Config

Pipeline configuration is TOML, loaded by a layered loader that walks to the monorepo root and parses into Pydantic models (`apps/pipeline/src/atr_pipeline/config/loader.py:11`). All pipeline/document config is TOML under `configs/`.

## Safety Gates (do not paraphrase — reference)

Hooks, CI guards, coordinator-ack, hook-bypass and admin-merge disclosure are load-bearing and detail-heavy. Read the authoritative rule files rather than restating them: `.claude/rules/{hooks,guards,merge-discipline}.md` and `CLAUDE.md` NEVER list.

## Quick Reference

| Need | Location |
|---|---|
| ruff / mypy config | `pyproject.toml` `[tool.ruff]` |
| Import layers | `pyproject.toml:91` |
| Atomic writes | `apps/pipeline/src/atr_pipeline/store/atomic_write.py` |
| oxlint rules | `apps/web/.oxlintrc.json` |
| Python rules (deep) | `.claude/rules/pipeline.md` |
| Web rules (deep) | `.claude/rules/web.md` |

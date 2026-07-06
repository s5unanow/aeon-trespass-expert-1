# Architecture Guide

**Project**: Aeon Trespass Expert — IR-first document compiler + static web reader (EN→RU rulebook translation)
**Style**: Modular monolith pipeline (Python) + static SPA reader (React), joined by a generated-schema contract
**Language**: Python 3.12 / TypeScript | **Framework**: typer + pydantic / React 19 + Vite 6

This is the root, system-level map. Deep detail is deliberately kept out of hot-path context: read `docs/PROJECT_ARCHITECTURE.md` (full design, ~3,400 lines) only for new ADRs, cross-system refactors, schema/IR shape changes, or onboarding — not for routine fixes (its own header says so). Decisions are recorded in `docs/adrs/ADR-001…013`. Per-module detail: `apps/pipeline/.ai-run/guides/architecture/architecture.md` and `apps/web/.ai-run/guides/architecture/architecture.md`.

## Architecture Overview

```
PDF ──► apps/pipeline (extract ► structure ► translate ► QA ► render)
              │ immutable, versioned artifacts (artifacts/, gitignored)
              ▼
      scripts/export_to_web.py ──► apps/web/public/documents/
              ▼
      apps/web static React reader (no backend)

packages/schemas: python (Pydantic, source) ─► jsonschema ─► ts (@atr/schemas)
```

**Key decisions** (see ADRs): the typed page IR is canonical state, not markdown (ADR-001/002); every stage output is an immutable, content-addressed artifact with human corrections as typed patches (ADR-003); PyMuPDF is the native extractor with Docling as layout evidence (ADR-004/005); QA is release-blocking (ADR-010); the reader is a static React app rendering typed nodes (ADR-008).

## Component Structure

| Path | Purpose | Evidence |
|---|---|---|
| `apps/pipeline/src/atr_pipeline/` | Compiler: cli, config, runner, stages, services, store, registry, eval, review | `apps/pipeline/pyproject.toml:40` (`atr` CLI entry) |
| `apps/web/src/` | Reader: app, routes, components, contexts, lib, styles | `apps/web/package.json:6-19` |
| `packages/schemas/` | Contract: `python/` (source) → `jsonschema/` + `ts/` (generated — never hand-edit) | `.claude/rules/schemas.md` |
| `configs/` | TOML configs: base, ci, documents, glossary, symbols, qa, golden_sets | `configs/base.toml` |
| `scripts/` | Codegen, export, CI guards (`check_*.py`), fixture bootstrap | `Makefile:14-24` |
| `artifacts/`, `var/` | Run outputs and runtime state — gitignored, never committed | `.gitignore` |

## Dependency Rules

| Rule | Enforced by |
|---|---|
| Pipeline import layers, no cycles | `uv run lint-imports` (in `make lint`) |
| Schema contract direction: Pydantic → JSON Schema → TS, never manual TS types | `make codegen` + `scripts/check_codegen_fresh.sh` (CI gate) |
| Web never imports pipeline; it consumes exported JSON bundles + `@atr/schemas` | workspace boundaries (`pnpm-workspace.yaml`, `apps/web/package.json:26`) |
| No web/pipeline file over 400 lines | `scripts/check_file_length.py`, oxlint `max-lines` |

Violations to avoid:

- ❌ Editing `packages/schemas/ts/` or `packages/schemas/jsonschema/` directly — regenerate via `make codegen`.
- ❌ Writing pipeline artifacts with `Path.write_text` — use `atr_pipeline.store.atomic_write` helpers (see `.claude/rules/pipeline.md`).
- ❌ Adding a stage side-effect without bumping the stage `version` — cached runs silently skip it (`.claude/rules/pipeline.md` § stage-output cache invalidation).

## Data Flow

1. `atr` CLI (`apps/pipeline/src/atr_pipeline/cli/`) runs stages via the runner with content-addressed caching (`runner/`).
2. Each stage reads upstream artifacts, writes new immutable artifacts to the store.
3. `make export` renders artifacts into `apps/web/public/documents/<doc>/`.
4. The reader routes (`apps/web/src/routes/`) fetch and render typed nodes; types come from `@atr/schemas`.

## Adding New Features

- **New pipeline stage / stage change**: follow `apps/pipeline/.ai-run/guides/architecture/architecture.md`; bump stage `version` on any new observable side-effect and add a cache-hit regression test.
- **New schema field**: edit `packages/schemas/python/`, run `make codegen`, commit generated outputs together (`packages/schemas/.ai-run/guides/development/schema-codegen.md`).
- **New reader surface**: `apps/web/.ai-run/guides/architecture/architecture.md`; changes to rendered output require visual verification and possibly baseline refresh (`.claude/rules/visual-verify.md`).
- **Extraction changes**: follow `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`; fixtures mandatory, golden refreshes in separate commits (`.claude/rules/extraction.md`).

## Quick Reference

| Need | Location |
|---|---|
| Entry point (pipeline) | `apps/pipeline/src/atr_pipeline/cli/main.py` (`atr` app) |
| Entry point (web) | `apps/web/src/main.tsx` |
| Stage implementations | `apps/pipeline/src/atr_pipeline/stages/` |
| Artifact store / atomic writes | `apps/pipeline/src/atr_pipeline/store/` |
| Shared schema models | `packages/schemas/python/` |
| Document/pipeline config | `configs/*.toml` |
| System design rationale | `docs/PROJECT_ARCHITECTURE.md`, `docs/adrs/` |

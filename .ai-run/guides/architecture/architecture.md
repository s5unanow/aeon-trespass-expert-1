# Architecture Guide

**Project**: Aeon Trespass Expert — IR-first document compiler + static web reader (EN→RU rulebook translation)
**Style**: Modular monolith (Python pipeline) + static SPA (React reader), bridged by generated schemas
**Language**: Python 3.12 (`pyproject.toml:5`) and TypeScript | **Frameworks**: pydantic/typer; React 19 + Vite + React Router 7

This is the system-level digest. The full design rationale is `docs/PROJECT_ARCHITECTURE.md` (3,400+ lines — read on demand for ADR drafting or cross-system refactors, not for routine fixes; see its "When to read this" header). Module-level detail lives in `apps/pipeline/.ai-run/guides/` and `apps/web/.ai-run/guides/`.

## Architecture Overview

```
PDF ──► apps/pipeline (ingest → extract_native + extract_layout → structure
        → symbols → glossary → translation → qa → render → publish)
        │  immutable, versioned artifacts + typed human patches
        ▼
   artifacts/ (gitignored run data) ──► make export ──► apps/web/public/documents/
        ▼                                                    ▼
packages/schemas: python (Pydantic, source of truth)     apps/web (static React reader,
        └──► jsonschema/ ──► ts/ (both generated)         renders typed IR nodes)
```

**Key decisions** (each has an ADR under `docs/adrs/`):

| Decision | ADR |
|---|---|
| Typed, immutable page IR is canonical state; markdown is export/debug only | `docs/adrs/ADR-001-ir-first-canonical-state.md:1`, ADR-002 |
| Immutable artifacts; human corrections are typed patch layers, never in-place edits | ADR-003 |
| PyMuPDF is the native PDF truth source; Docling provides layout evidence only | ADR-004, ADR-005 |
| Curated symbol catalog + template matching for inline icons | ADR-006 |
| Translation runs on structured block-level units with schema-constrained outputs | ADR-007 |
| Reader is a static React app rendering typed nodes (no server) | ADR-008 |
| QA is release-blocking | ADR-010 |
| Shared schemas generated Pydantic → JSON Schema → TS (never manual TS types) | ADR-011 |

## Component Structure

```
apps/pipeline/       Python content compiler (uv workspace member)
apps/web/            React 19 / Vite static reader (pnpm workspace member)
packages/schemas/    python/ (Pydantic) → jsonschema/ → ts/ (generated)
configs/             TOML configs: base, ci, documents, glossary, symbols, qa
scripts/             Codegen, export-to-web, CI guard scripts (check_*.py)
artifacts/           Pipeline run output (gitignored)
docs/                Architecture doc + ADRs + extraction playbook (read on demand)
```

## Dependency Rules

Pipeline layers are machine-enforced by import-linter (`pyproject.toml:94-104`):

```
cli → runner → stages | eval → services | store | registry → config → utils
```

| Rule | Enforced by |
|---|---|
| Lower layers never import higher layers; no cycles | `lint-imports` (part of `make lint`) |
| `stages` may import `runner.stage_context` (runtime dataclass) but not orchestration logic | contract comment `pyproject.toml:105-106` |
| Web never hand-writes types for pipeline data — imports `@atr/schemas` | `apps/web/package.json` devDependency `@atr/schemas: workspace:*` |
| Generated dirs (`packages/schemas/{jsonschema,ts}`) are never edited directly | `make check-codegen` in CI; `.claude/rules/schemas.md` |

## Data Flow

1. `atr_pipeline.cli` plans a run; `runner/executor.py` executes stages with content-addressed caching (`runner/cache_keys.py` — cache key includes `stage_v={stage_version}`, so a stage gaining a new side-effect must bump its `version`; see `.claude/rules/pipeline.md`).
2. Each stage writes immutable artifacts through `store/artifact_store.py` using atomic writes (`store/atomic_write.py`).
3. `make export` (`scripts/export_to_web.py`) publishes the bundle to `apps/web/public/documents/`.
4. The reader loads the bundle statically and renders typed nodes; routes follow `/documents/<doc>/<edition>/<pageId>`.

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|---|---|
| Change data shapes in `packages/schemas/python/` then `make codegen` | Hand-edit `packages/schemas/ts/` or `jsonschema/` |
| Add stage outputs via `artifact_store` + atomic writes and bump the stage `version` | Plain `Path.write_text` for artifacts; silent cache-shape changes |
| Fix rendering in `apps/web/src/` and verify visually | Patch exported bundle files under `public/documents/` |
| Rely on path-triggered `.claude/rules/*.md` for module conventions | Front-load the 3,400-line architecture doc for a one-file fix |

## Quick Reference

| Need | Location |
|---|---|
| Pipeline entry point | `apps/pipeline/src/atr_pipeline/cli/` |
| Stage implementations | `apps/pipeline/src/atr_pipeline/stages/<stage>/` |
| Executor + caching | `apps/pipeline/src/atr_pipeline/runner/executor.py`, `cache_keys.py` |
| Artifact store / atomic IO | `apps/pipeline/src/atr_pipeline/store/` |
| Schema source of truth | `packages/schemas/python/` |
| Reader routes/components | `apps/web/src/routes/`, `apps/web/src/components/` |
| Pipeline/document config | `configs/*.toml`, `configs/documents/` |
| Export to web | `scripts/export_to_web.py` (`make export`) |

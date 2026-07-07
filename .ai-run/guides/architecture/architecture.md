# Architecture Guide

**Project**: aeon-trespass-expert
**Style**: IR-first modular monolith (two apps + a shared schema bridge), not microservices
**Language**: Python 3.12 (`apps/pipeline`) | TypeScript/React 19 (`apps/web`)

Full design rationale: `docs/PROJECT_ARCHITECTURE.md` and `docs/adrs/ADR-001` through `ADR-013`. Read those on demand for a cross-system refactor or new ADR — this guide is the day-to-day reference.

---

## Architecture Overview

```
PDF --> [apps/pipeline stages] --> IR artifacts (JSON, content-addressed)
                                        |
                                        v
                          scripts/export_to_web.py
                                        |
                                        v
                        apps/web/public/documents/**
                                        |
                                        v
                          apps/web (static React reader)
```

**Key decision** (ADR-001, ADR-002): the pipeline treats the PDF as two evidence streams (native PDF objects + layout/OCR evidence) fused into a typed, immutable page IR. Markdown is an export/debug format only, never the canonical state — this rules out treating any generated `.md` as a source of truth.

---

## Component Structure

```
apps/pipeline/src/atr_pipeline/
├── stages/            One package per pipeline stage (extract_native, extract_layout,
│                       structure, symbols, glossary, translation, qa, render, publish,
│                       patch, ingest, assistant)
├── runner/             Stage executor, cache-key computation, manifest building
├── services/           Cross-stage services (pdf, llm, assets)
├── store/               Artifact store + atomic_write helpers
├── registry/            Stage registration
└── cli/commands/        Typer CLI entry points (`atr ...`)

apps/web/src/
├── routes/               React Router 7 route components (ReaderPage, DocumentIndexPage, ...)
├── components/           reader/, layout/, nav/, glossary/ — presentational + feature components
├── lib/                  api/ (fetch loaders), render/ (typed render-node helpers), feedback/
├── contexts/             React context providers (PageContext)
└── app/                  App.tsx, router.tsx — router wiring

packages/schemas/
├── python/atr_schemas/    Canonical Pydantic models (source of truth)
├── jsonschema/            Generated JSON Schema (never hand-edited)
└── ts/src/generated/       Generated TS types (never hand-edited)
```

---

## Key Abstractions: Schema Contracts

**Pattern**: every artifact exchanged between pipeline stages, and between pipeline and web, is a Pydantic model in `packages/schemas/python/atr_schemas/*.py` — e.g. `QASummaryV1` (`packages/schemas/python/atr_schemas/qa_summary_v1.py:17`). `make codegen` regenerates `packages/schemas/jsonschema/*.schema.json` and `packages/schemas/ts/src/generated/**` from these models; both generated trees are read-only.

**Rule**: never write a TypeScript type by hand for data that crosses the pipeline/web boundary — add or change the Pydantic model, run `make codegen`, and `make check-codegen` verifies freshness.

| ✅ DO | ❌ DON'T |
|-------|----------|
| Add/change a field on the Pydantic model, then `make codegen` | Hand-write or hand-edit a `.ts` type in `packages/schemas/ts/` |
| Treat `packages/schemas/jsonschema/**` as generated output | Edit `packages/schemas/jsonschema/**` directly |

---

## Stage Execution Model

Every pipeline stage implements a `version` field (e.g. `apps/pipeline/src/atr_pipeline/stages/qa/stage.py:51`) that feeds `build_cache_key()` (`apps/pipeline/src/atr_pipeline/runner/cache_keys.py:7`) alongside `schema_version`, `config_hash`, and input hashes. The executor (`apps/pipeline/src/atr_pipeline/runner/executor.py`) short-circuits `run()` entirely on a cache-key hit.

**Invariant**: any new artifact write or side effect added inside a stage's `run()` requires bumping that stage's `version` in the same change, or the new side effect silently never appears on cached re-runs (see `.ai-run/guides/development/pipeline-development.md` for the full rule and required regression-test shape).

---

## Immutable Artifacts

Every stage output is content-addressed and written via `atomic_write_bytes` / `atomic_write_text` (`apps/pipeline/src/atr_pipeline/store/atomic_write.py:10`) — temp file, `fsync`, then `os.replace`, so a crash never exposes a partially-written artifact. Human corrections are checked in as typed patch layers (`stages/patch/`), never edited in place (ADR-003).

---

## Data Flow (reader request)

```
Browser --> React Router route (apps/web/src/app/router.tsx) --> route component
        --> lib/api/loadRenderPage() --> apps/web/public/documents/<doc>/<edition>/<page>
        --> typed RenderPageData --> BlockRenderer / FacsimilePage components
```

Example: `ReaderPage` (`apps/web/src/routes/ReaderPage.tsx:14`) loads a page via `loadRenderPage()` in a `useEffect`, guards against stale/aborted requests with an `AbortController`, and renders through `BlockRenderer`.

---

## Adding New Features

**To add a new pipeline stage**: create a package under `apps/pipeline/src/atr_pipeline/stages/<name>/`, implement the stage protocol (`apps/pipeline/src/atr_pipeline/runner/stage_protocol.py`), register it in `registry/`, add a Pydantic output model in `packages/schemas/python/atr_schemas/`, run `make codegen`.

**To add a new reader route**: add a component under `apps/web/src/routes/`, register it in `apps/web/src/app/router.tsx` (lazy-load if it is not on the primary reading path, per the `QaDashboard` pattern at `apps/web/src/app/router.tsx:9`).

---

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|-------|----------|
| Add fields via the Pydantic model + `make codegen` | Hand-edit generated JSON Schema or TS types |
| Bump stage `version` when `run()` gains a new side effect | Add a new artifact write without a version bump |
| Write artifacts via `atomic_write_bytes`/`atomic_write_text` | Use plain `Path.write_text`/`write_bytes` for artifact output |
| Treat `docs/` as read-on-demand, not memorized | Load `docs/PROJECT_ARCHITECTURE.md` (3465 lines) for a single-file fix |

---

## Quick Reference

| Need | Location |
|------|----------|
| Pipeline stages | `apps/pipeline/src/atr_pipeline/stages/` |
| Stage executor / cache keys | `apps/pipeline/src/atr_pipeline/runner/` |
| Artifact store / atomic writes | `apps/pipeline/src/atr_pipeline/store/` |
| Canonical schemas | `packages/schemas/python/atr_schemas/` |
| Reader routes | `apps/web/src/routes/` |
| Reader components | `apps/web/src/components/` |
| Design rationale (read on demand) | `docs/PROJECT_ARCHITECTURE.md`, `docs/adrs/` |

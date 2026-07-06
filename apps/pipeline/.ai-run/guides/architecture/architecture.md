# Architecture Guide — apps/pipeline

**Project**: atr-pipeline (`apps/pipeline/pyproject.toml:2`)
**Style**: Layered modular monolith — stage/runner/store layering enforced by import-linter
**Language**: Python 3.12 | **Framework**: typer CLI + pydantic models, uv workspace

Authoritative long-form docs (this guide summarizes, does not duplicate):
`docs/PROJECT_ARCHITECTURE.md` and `docs/adrs/` at the repo root — notably
ADR-001 (IR-first canonical state), ADR-003 (immutable artifacts and patches),
ADR-009 (no workflow orchestrator in v1), ADR-010 (QA is release-blocking).
Conventions in `.claude/rules/pipeline.md` remain authoritative over this guide.

---

## Architecture Overview

```
cli  ──►  runner  ──►  stages | eval  ──►  services | store | registry  ──►  config  ──►  utils
```

Each stage is a plain class implementing the `Stage` protocol; the runner
executes stages with content-hash caching and records events in a SQLite
registry; all outputs land in an immutable, content-addressed artifact store.

**Key decision**: IR (intermediate representation) is the canonical state, not
Markdown or the PDF — every stage reads and writes versioned pydantic IR
artifacts (ADR-001, ADR-002).

---

## Component Structure

```
apps/pipeline/src/atr_pipeline/
├── cli/        Typer entrypoint + commands (main.py:14 `app = typer.Typer(...)`)
├── runner/     Stage protocol, executor, cache keys, plan, stage registry
├── stages/     ingest, extract_native, extract_layout, symbols, structure,
│               translation, render, qa, publish, assistant, glossary, patch
├── eval/       Deterministic scorers, benchmarks, invariants, thresholds
├── services/   llm, pdf, assets — external-facing adapters
├── store/      ArtifactStore, ArtifactRef, atomic_write, pathing
├── registry/   SQLite run/event registry (db.py:42 `open_registry`)
├── config/     TOML loader + pydantic config models (models.py:17)
└── utils/      hashing (bottom layer, no inward deps)
```

---

## Data Flow — IR-first compile

Default stage order per `runner/registry.py:20-35` (`build_stage_registry`):

```
PDF ─► ingest ─► extract_native ─► extract_layout ─► symbols ─► structure
        ─► translate ─► style critic/repair ─► render ─► qa ─► chunk_export ─► publish
```

1. `cli/commands/run.py:39` (`run`) builds the plan and a `StageContext`
   (`runner/stage_context.py:15`).
2. `runner/executor.py:23` (`execute_stage`) computes a cache key, checks the
   registry for a completed event, and either replays the cached artifact ref
   or runs the stage.
3. Stage output (a pydantic `BaseModel`) is persisted via
   `ctx.artifact_store.put_json` (`runner/executor.py:102`).
4. QA gates publishability (ADR-010); publish/export produce the web bundle.

---

## Stage Protocol and Executor Caching

The contract every stage implements — `runner/stage_protocol.py:13-25`:
`name`, `scope` (`StageScope`), `version`, and
`run(ctx: StageContext, input_data: BaseModel | None) -> BaseModel`.

| Concern | Where |
|---|---|
| Cache key includes `stage_v={stage_version}` | `runner/cache_keys.py:25` |
| Cache lookup + cached-event replay | `runner/executor.py:48-84` |
| Dangling-ref self-heal (missing artifact ⇒ re-run) | `runner/executor.py:142-183` |
| Stage-supplied extra cache inputs (external files) | `runner/executor.py:44-46` |
| Cached event record for manifests | `runner/executor.py:62-77` |

**Cache-invalidation rule (S5U-662)**: any new observable side-effect in a
stage's `run()` requires a `version` bump in the same PR plus a cache-hit
regression test. Canonical bump-comment example: `stages/qa/stage.py:51-61`.
Full rule: `.claude/rules/pipeline.md` § "Stage-output cache invalidation".

---

## Artifact Store Immutability

`store/artifact_store.py:30` — artifacts are content-addressed JSON files;
writing identical content returns the existing ref without rewriting
(`put_json`, `store/artifact_store.py:45-77`). All writes go through
`atomic_write_text` (`store/artifact_store.py:76`), backed by
temp-file + `fsync` + `os.replace` (`store/atomic_write.py:11-36`).

| Avoid | Prefer |
|---|---|
| Mutating an existing artifact file in place | New content ⇒ new content hash ⇒ new file; corrections ship as patches (ADR-003) |
| `Path.write_text` / `write_bytes` for artifacts | `atomic_write_bytes` / `atomic_write_text` — `store/atomic_write.py:11,39` |
| Returning a cached ref without checking disk | `_cached_artifact_present` fall-through re-run — `runner/executor.py:142` |

---

## Import-Layer Contract

Enforced by `lint-imports` (`uv run lint-imports`, wired into `make lint`).
Layers declared in the root `pyproject.toml:94-104`:

```
cli → runner → (stages | eval) → (services | store | registry) → config → utils
```

Documented, intentional exceptions live in `ignore_imports`
(root `pyproject.toml:116-132`) — e.g. every `stages/*/stage.py` may import
`runner.stage_context` (the runtime dataclass) but never executor/registry/plan
orchestration logic (rationale comments at root `pyproject.toml:105-115`).

**Violations to avoid:**
- A stage importing `runner.executor` or `runner.registry` (orchestration).
- `services`/`store` importing upward into `stages` (except the documented
  `raster_provider -> artifact_store` bridge, root `pyproject.toml:121`).

---

## Adding a New Stage

1. Create `stages/<name>/stage.py` with a class satisfying the `Stage`
   protocol (`runner/stage_protocol.py:13`); IO types are pydantic models
   from `packages/schemas/python/`.
2. Register it in `build_stage_registry` (`runner/registry.py:20`).
3. If it imports `runner.stage_context`, add the documented `ignore_imports`
   entry in the root `pyproject.toml` (pattern at lines 122-131).
4. Persist extra outputs via `ctx.artifact_store.put_json` /
   `atomic_write_*` only, and bump `version` per the S5U-662 rule with a
   cache-hit regression test (see `apps/pipeline/.ai-run/guides/testing/testing-patterns.md`).

---

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|-------|----------|
| Treat IR artifacts as the canonical state (ADR-001) | Treat Markdown/PDF text dumps as source of truth (ADR-002) |
| Write artifacts through `ArtifactStore` / `atomic_write_*` | Hand-roll `open(...).write()` for artifact outputs |
| Bump `stage.version` when `run()` gains a side-effect | Ship a new artifact write against an unchanged cache key |
| Keep imports flowing down the declared layers | Add undocumented `ignore_imports` entries |

## Quick Reference

| Need | Location |
|------|----------|
| CLI entry point | `apps/pipeline/src/atr_pipeline/cli/main.py:14` |
| Stage execution + caching | `apps/pipeline/src/atr_pipeline/runner/executor.py:23` |
| Stage registry / pipeline order | `apps/pipeline/src/atr_pipeline/runner/registry.py:20` |
| Artifact storage | `apps/pipeline/src/atr_pipeline/store/artifact_store.py:30` |
| Run/event registry (SQLite) | `apps/pipeline/src/atr_pipeline/registry/events.py:48` |
| Config models + TOML loader | `apps/pipeline/src/atr_pipeline/config/models.py:17` |
| Layer contract | root `pyproject.toml:91-132` |
| Long-form architecture + ADRs | `docs/PROJECT_ARCHITECTURE.md`, `docs/adrs/` |

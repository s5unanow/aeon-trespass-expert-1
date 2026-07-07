# apps/pipeline — Architecture Guide

IR-first document compiler: `PDF -> IR -> translate -> QA -> site bundle`. Python 3.12, typer CLI, pydantic models, PyMuPDF/Docling extraction, hatchling build, pytest. This guide captures the load-bearing conventions. For the authoritative rules see `.claude/rules/pipeline.md`; for design rationale see `docs/adrs/` (10 ADRs, `docs/adrs/ADR-001-ir-first-canonical-state.md` onward).

## Architecture Overview

The pipeline is a sequence of deterministic, cache-keyed **stages** that transform an immutable **Intermediate Representation (IR)**. Each stage reads prior artifacts from a content-addressed store, produces a new pydantic artifact, and records an event in a SQLite registry. There is no external workflow engine (ADR-009); ordering is a static list and execution is a plain executor loop.

- IR is canonical state; Markdown/site output is a projection, never source of truth (`docs/adrs/ADR-002-markdown-not-source-of-truth.md`).
- Artifacts are immutable + content-addressed; corrections flow through patches, not mutation (`docs/adrs/ADR-003-immutable-artifacts-and-patches.md`).
- Stage order is defined declaratively in `apps/pipeline/src/atr_pipeline/runner/plan.py:6` (`WALKING_SKELETON_STAGES`), with an EN-only variant `SOURCE_ONLY_STAGES` at `apps/pipeline/src/atr_pipeline/runner/plan.py:22` that drops the translate stages.

## Component Structure

Top-level package `apps/pipeline/src/atr_pipeline/` (import direction flows top→bottom, see Import Layers):

| Package | Responsibility |
|---------|----------------|
| `cli/` | Typer entrypoint (`cli/main.py:14`) + subcommands in `cli/commands/` (`run.py`, `qa.py`, `ingest.py`, `patch.py`, `release.py`, …) |
| `runner/` | Orchestration: executor, cache keys, plan, stage protocol, run context |
| `stages/` | The 12 stage implementations (one subpackage each) |
| `eval/` | Deterministic scorers/policies (confidence bands) consumed by stages |
| `services/` | Side-effecting adapters: `llm/`, `pdf/`, `assets/` |
| `store/` | Content-addressed artifact store + atomic writes + pathing |
| `registry/` | SQLite run/event ledger (`registry/db.py`, `registry/events.py`) |
| `config/` | Layered TOML loader + pydantic config models |
| `review/`, `logging/`, `utils/` | Supporting helpers (`logging/__init__.py` is a namespace marker; the pipeline uses stdlib `logging.getLogger`) |

Stage subdirectories (each a self-contained package with a `stage.py`): `ingest`, `extract_native`, `extract_layout`, `symbols`, `structure`, `translation`, `render`, `qa`, `publish`, `patch`, `glossary`, `assistant`.

## Stage & Executor Model

### Stages implement a structural Protocol, not a base class

A stage is any object satisfying the `Stage` Protocol — `name`, `scope`, `version` properties and a `run(ctx, input_data)` method (`apps/pipeline/src/atr_pipeline/runner/stage_protocol.py:12`). No inheritance is required; conformance is duck-typed (`@runtime_checkable`).

- Best: expose `version` as a `@property` returning a string literal, e.g. `apps/pipeline/src/atr_pipeline/stages/qa/stage.py:51` (`return "1.11"`).
- Best: `run()` receives a `StageContext` dataclass carrying `run_id`, `document_id`, `config`, `artifact_store`, `registry_conn`, `logger`, `page_filter` (`apps/pipeline/src/atr_pipeline/runner/stage_context.py:14`). Stages depend on this context dataclass but must NOT import orchestration logic (executor/registry/plan) — enforced by the layer contract's `ignore_imports` allowlist.

### The executor: cache-check → run → record

`execute_stage` builds a cache key, checks the registry for a matching completed event, and either serves the cached artifact or runs the stage and records the result (`apps/pipeline/src/atr_pipeline/runner/executor.py:23`).

- The cache key folds stage name, `version`, schema version, config hash, and input hashes (`apps/pipeline/src/atr_pipeline/runner/cache_keys.py:8`).
- A cache hit is served ONLY if the artifact still exists on disk — a dangling ref falls through and re-runs (`apps/pipeline/src/atr_pipeline/runner/executor.py:142`, self-heal from `make clean`).
- Stage `run()` exceptions are recorded as a `failed` event with the error message, never swallowed silently (`apps/pipeline/src/atr_pipeline/runner/executor.py:125`).

### Cache invalidation rule (the #1 pipeline footgun)

Because `stage_version` is part of the cache key, **any new observable side-effect added to `run()` (a new `put_json`/`put_binary`, a new persisted record) MUST bump the stage's `version` in the same PR, plus a cache-hit regression test.** An unchanged version means cached runs silently skip the new side-effect. Full rule + worked test shape in `.claude/rules/pipeline.md` ("Stage-output cache invalidation").

| Bad | Best |
|-----|------|
| Add `ctx.artifact_store.put_json(...)` to `run()`, leave `version` unchanged | Add the write AND bump `version` (`stages/ingest/stage.py:30` documents its `1.1 -> 1.2` bump inline) |
| No test for the cached path | Add a test asserting the side-effect survives a cache hit (see `tests/unit/stages/qa/test_stage_version.py`) |

## Artifact Store

All artifact output goes through content-addressed, atomic writes — never plain `Path.write_text`/`write_bytes`.

- `atomic_write_bytes` / `atomic_write_text` write to a temp file, loop until every byte is on disk, `fsync`, then `os.replace` (`apps/pipeline/src/atr_pipeline/store/atomic_write.py:11`). A short write is never renamed into place as a truncated-but-committed artifact.
- The store dedupes by content hash: identical content returns the existing ref without rewriting, only touching mtime (`apps/pipeline/src/atr_pipeline/store/artifact_store.py:45`).
- `ArtifactStore.put_binary` also routes through `atomic_write_bytes` (`apps/pipeline/src/atr_pipeline/store/artifact_store.py:110`).

| Bad | Best |
|-----|------|
| `path.write_text(json.dumps(...))` | `atomic_write_text(path, ...)` via the store's `put_json` |
| Hand-built output paths | `store.put_json(document_id=..., schema_family=..., scope=..., entity_id=..., data=model)` |

## Import Layers

`lint-imports` enforces a strict layered contract (`pyproject.toml:94`, root `pyproject.toml`). Higher layers may import lower; the reverse is forbidden. Layers, top (highest) to bottom:

1. `atr_pipeline.cli`
2. `atr_pipeline.runner`
3. `atr_pipeline.stages` | `atr_pipeline.eval`
4. `atr_pipeline.services` | `atr_pipeline.store` | `atr_pipeline.registry`
5. `atr_pipeline.config`
6. `atr_pipeline.utils`

Documented, reviewer-visible exceptions live in `ignore_imports` (`pyproject.toml:116`) — notably every stage's `stage.py -> runner.stage_context` (stages need the runtime context dataclass but not the orchestrator). Adding a new cross-layer import means either it flows downward (allowed) or it is added to `ignore_imports` with a rationale comment.

## Logging & Config conventions

### Logging — stdlib, module-scoped

Existing pipeline code uses `logging.getLogger(__name__)`, NOT `structlog`. Do not migrate existing stdlib-logging code just to satisfy a rule; prefer `structlog` only for genuinely new structured-context services (`.claude/rules/pipeline.md`).

- Best: `log = logging.getLogger(__name__)` at module scope, e.g. `apps/pipeline/src/atr_pipeline/services/llm/anthropic_adapter.py:19`.
- The `StageContext.logger` defaults to `logging.getLogger("atr_pipeline")` (`apps/pipeline/src/atr_pipeline/runner/stage_context.py:24`).
- Never `print()` for diagnostics; never a bare `except Exception` without logging the context.

### Config — layered TOML + pydantic

Configuration is TOML under `configs/` (`base.toml`, `ci.toml`, `documents/`, `qa/`, `glossary/`, `symbols/`, `golden_sets/`), loaded and validated into pydantic models.

- The loader walks up to the monorepo root (dir containing both `configs/` and `.git`) and layers TOML files (`apps/pipeline/src/atr_pipeline/config/loader.py:11`).
- Config is parsed into `DocumentBuildConfig` (`apps/pipeline/src/atr_pipeline/config/models.py`), the pydantic model threaded through `StageContext.config`.
- An env var must never flip a safety gate's default — CLI-flag escape hatches only (e.g. `publish_review_only`, `apps/pipeline/src/atr_pipeline/runner/stage_context.py:30`).

## Testing conventions

Tests live under `apps/pipeline/tests/` split into `unit/`, `integration/`, `contract/`, and `safety_gate_corpus/` (266 `test_*.py` files). Test tree mirrors the source tree (`tests/unit/stages/qa/`, `tests/unit/runner/`, `tests/unit/store/`, …).

- Markers are declared in `pyproject.toml:137`: `slow` (skipped by the pre-commit fast subset) and `codex_live` (opt-in real-CLI smoke via `ATR_CODEX_LIVE_SMOKE=1`).
- Shared fixtures are auto-discovered from `apps/pipeline/tests/unit/conftest.py:1` (no explicit import needed).
- Cache-hit regression tests are mandatory for new stage side-effects — see `tests/unit/stages/translation/test_stage_cache_hit_s5u734.py` and `tests/unit/stages/qa/test_stage_version.py`.
- Every new test needs red-before evidence in the commit/PR (`.claude/rules/hooks.md`, "Three-input test discipline").

## Boundaries Summary

| DO | DON'T |
|----|-------|
| Implement stages against the `Stage` Protocol (`runner/stage_protocol.py:12`) | Add a shared stage base class or import the executor from a stage |
| Bump `version` + add a cache-hit test on any new `run()` side-effect | Add a `put_json`/`put_binary` and leave `version` unchanged |
| Write artifacts via the store / `atomic_write_*` (`store/atomic_write.py:11`) | Use `Path.write_text`/`write_bytes` for artifact output |
| Keep imports flowing down the layer stack (`pyproject.toml:94`) | Import upward; add a cross-layer edge without an `ignore_imports` rationale |
| Use `logging.getLogger(__name__)` (`services/llm/anthropic_adapter.py:19`) | Use `print()` or a bare `except Exception` without logging |
| Gate behavior via explicit CLI flags | Flip a gate default from an ambient env var |
| Read `.claude/rules/pipeline.md` + `docs/adrs/` before deep changes | Restate those docs here |

# Architecture Guide — apps/pipeline

**Project**: aeon-trespass-expert / `atr-pipeline` (`pyproject.toml:2-3`)
**Style**: Layered, contract-enforced by `import-linter`
**Language**: Python 3.12 | **Framework**: pydantic (models) + typer (CLI)

---

## Architecture Overview

```
atr_pipeline.cli               (Typer commands)
      |
      v
atr_pipeline.runner            (plan, executor, stage_context, registry glue)
      |
      v
atr_pipeline.stages | atr_pipeline.eval   (domain logic + evaluation harness)
      |
      v
atr_pipeline.services | atr_pipeline.store | atr_pipeline.registry
      |
      v
atr_pipeline.config
      |
      v
atr_pipeline.utils
```

**Key decision**: the layering is not just convention — it is a machine-checked
contract (`pyproject.toml:94-132`, `[[tool.importlinter.contracts]]`, type
`"layers"`). `make lint` runs `uv run lint-imports` (`Makefile:14`), so a stage
importing `runner.executor` (orchestration) instead of `runner.stage_context`
(runtime data) fails CI, not just review.

---

## Component Structure

```
apps/pipeline/src/atr_pipeline/
├── cli/                 Typer entrypoint + per-command modules (cli/commands/)
├── runner/              Orchestration: plan, executor, cache_keys, stage_context
├── stages/               One package per pipeline phase (ingest, extract_native,
│                         extract_layout, symbols, structure, translation, render,
│                         qa, publish, assistant, glossary, patch)
├── eval/                 Evaluation/audit harness: confidence scoring, invariants,
│                         cross-stage ref checks, golden comparison, benchmarking
├── services/             External integrations: llm/ (translation adapters),
│                         pdf/ (rasterization), assets/ (symbol/image resolution)
├── store/                Content-addressed artifact store + atomic writes
├── registry/             SQLite run/stage-event bookkeeping
├── config/                TOML loader + Pydantic config models
└── utils/                 Hashing primitives (sha256, content_hash)
```

---

## Design Patterns Detected

| Pattern | Usage | Location |
|---------|-------|----------|
| Protocol (structural typing) | `Stage` — every pipeline stage implements `name`/`scope`/`version`/`run` without inheriting a base class | `runner/stage_protocol.py:13-25` |
| Protocol (structural typing) | `TranslatorAdapter` — every LLM provider adapter implements `translate_batch` | `services/llm/base.py:33-44` |
| Strategy | `QARule` protocol + `get_all_rules()` returns 11 rule instances, each independently evaluating a `QAPageContext` | `stages/qa/registry.py:44-235` |
| Factory | `create_translator()` builds the configured `TranslatorAdapter` from `TranslationConfig.provider`, rejecting cross-provider option leakage before construction | `services/llm/factory.py:232-298` |
| Decorator | `FallbackTranslator` wraps a primary adapter with a fallback adapter + retry loop when `fallback_provider` is configured | `services/llm/factory.py:280-298`, `services/llm/fallback.py` |
| Registry map | `build_stage_registry()` maps stage names to `Stage` instances consumed by the executor | `runner/registry.py:20-35` |
| Content-addressed store | `ArtifactStore.put_json`/`put_bytes` write once per content hash; repeat writes just bump mtime | `store/artifact_store.py:45-120` |

### Primary Pattern: Stage protocol

```python
# Source: runner/stage_protocol.py:13-25
class Stage(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def scope(self) -> StageScope: ...
    @property
    def version(self) -> str: ...
    def run(self, ctx: StageContext, input_data: BaseModel | None) -> BaseModel: ...
```

**When to use**: every new pipeline phase (`stages/<name>/stage.py`) implements
this protocol directly — no shared base class, no `super().__init__()`. The
executor (`runner/executor.py`) only ever calls these four members.

---

## Layer/Module Responsibilities

| Component | Responsibility | Depends On | Depended By |
|-----------|----------------|------------|-------------|
| `cli` | Typer commands; parse args, load config, invoke the runner | `runner`, `config` | (top-level) |
| `runner` | Orchestrate execution: stage ordering (`plan.py`), cache-checked execution (`executor.py`), per-invocation runtime deps (`stage_context.py`), stage-name registry (`registry.py`) | `stages`, `eval`, `services`, `store`, `registry`, `config`, `utils` | `cli` |
| `stages` | One package per pipeline phase; each implements the `Stage` protocol | `services`, `store`, `registry`, `config`, `utils`; narrowly `runner.stage_context` and `eval` (named exceptions below) | `runner` |
| `eval` | Confidence scoring/policy, invariants, cross-stage ref checks, golden comparison, benchmarking, audit reports | `services`, `store`, `registry`, `config`, `utils` | `stages` (2 named exceptions), `cli` (`eval_cmd.py`) |
| `services` | LLM adapters (`llm/`), PDF rasterization (`pdf/`), asset resolution (`assets/`) | `config`, `utils`; narrowly `store` (1 named exception) | `stages`, `eval` |
| `store` | Content-addressed artifact store, atomic writes, edition selection | `config`, `utils` | `services`, `stages`, `eval`, `runner` |
| `registry` | SQLite run/stage-event tracking | `config`(none directly), `utils` | `runner`, `stages` |
| `config` | TOML loader (`loader.py`) + Pydantic models (`models.py`) | `utils` | every layer above |
| `utils` | SHA-256 / content hashing | — | every layer above |

---

## Dependency Rules

```
cli ──► runner ──► stages | eval ──► services | store | registry ──► config ──► utils
```

| Rule | Enforced By |
|------|-------------|
| No layer imports a layer above it (e.g. `stages` must not import `runner.executor`) | `import-linter` layers contract, `pyproject.toml:94-104` |
| A stage may import `runner.stage_context` (runtime data) but not orchestration logic (`executor`, `plan`, `registry`) | Explicit per-stage `ignore_imports` entries, `pyproject.toml:116-131` |
| `stages.structure` may import `eval.confidence_scorer`; `stages.qa` may import `eval.confidence_policy` | Named exceptions, `pyproject.toml:109-110, 117-119` |
| `services.pdf.raster_provider` may import `store.artifact_store` (bridges rendering and content-addressed storage) | Named exception, `pyproject.toml:114-115, 121` |

**Violations to avoid:**
- A stage importing `runner.executor` or `runner.plan` directly instead of only `runner.stage_context`.
- Adding a new cross-layer import without adding the matching `ignore_imports` line and a one-line rationale comment in `pyproject.toml` — `lint-imports` fails the build otherwise.

---

## Data Flow

**Example flow** (`atr run --doc <id>`):
1. `cli/commands/run.py` loads `DocumentBuildConfig` and resolves the stage list via `runner/plan.py:35-68` (`resolve_stage_range`).
2. For each stage, `runner/executor.py:23-140` (`execute_stage`) builds a deterministic cache key (`runner/cache_keys.py:8-35`) from stage name/version, config hash, and input hashes.
3. On a cache miss, `stage.run(ctx, input_data)` executes; the returned pydantic model is written via `ctx.artifact_store.put_json(...)` (`store/artifact_store.py:45-77`), content-addressed by SHA-256.
4. The registry (`registry/events.py:10-46`) records a `stage_events` row (`started` → `completed`/`failed`/`cached`) keyed by the same cache key, so a later run with identical inputs short-circuits via `find_cached_event`.
5. `runner/manifest_builder.py` / `summary_builder.py` assemble the run-level manifest consumed by `atr export` / the web bundle.

---

## Key Abstractions

| Abstraction | Purpose | Implementations |
|-------------|---------|-----------------|
| `Stage` (Protocol) | Canonical execution interface every pipeline phase implements | 12 stage classes registered in `runner/registry.py:22-35` |
| `TranslatorAdapter` (Protocol) | Canonical interface for LLM translation providers | `MockTranslator`, `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`, `GeminiCLIAdapter`, `CodexCLIAdapter`, `AgyCLIAdapter`, `FallbackTranslator` — see `services/llm/factory.py:155-229` |
| `QARule` (Protocol) | Canonical interface for a single QA check | 11 rule classes in `stages/qa/registry.py:56-219` |
| `ArtifactRef` | Immutable pointer into the content-addressed store: `{document_id}/{schema_family}/{scope}/{entity_id}/{content_hash}.json` | `store/artifact_ref.py:8-25` |

---

## Adding New Features

### To add a new pipeline stage:

1. Create `stages/<name>/stage.py` implementing the `Stage` protocol (`name`, `scope`, `version`, `run`).
2. If `run()` needs `StageContext`, add an explicit `ignore_imports` line for `atr_pipeline.stages.<name>.stage -> atr_pipeline.runner.stage_context` in `pyproject.toml` (`[tool.importlinter]`, following the existing 12 entries at lines 122-131) — otherwise `lint-imports` fails.
3. Register the instance in `build_stage_registry()` (`runner/registry.py:20-35`).
4. Add the stage name to `WALKING_SKELETON_STAGES` (and `SOURCE_ONLY_STAGES` if it should also run in EN-only/`--edition en` mode) in `runner/plan.py:6-32`.
5. If `run()` writes any new artifact, bump `version` in the same PR — see `.claude/rules/pipeline.md` § "Stage-output cache invalidation" and `development-practices.md` in this guide set.

### To add a new translation provider:

1. Implement `TranslatorAdapter` (`translate_batch`) in `services/llm/<provider>_adapter.py`.
2. Add the provider name to `_CLI_PROVIDERS`/`_API_PROVIDERS`/`_NO_OPTIONS_PROVIDERS` in `services/llm/factory.py:18-24`.
3. Add a construction branch in `_create_single_adapter` (`services/llm/factory.py:155-229`).

---

## Configuration & Environment

| Config Type | Location | Accessed Via |
|-------------|----------|--------------|
| Base + env + document TOML | `configs/base.toml`, `configs/{env}.toml`, `configs/documents/{id}.toml` | `config/loader.py:46-90` (`load_document_config`, 3-layer deep-merge) |
| Typed config model | Pydantic models | `config/models.py` (`DocumentBuildConfig`, `PipelineConfig`, `TranslationConfig`, …) |
| Per-run runtime deps | Not config, but injected per stage invocation | `runner/stage_context.py:14-38` (`StageContext` dataclass: `run_id`, `document_id`, `config`, `artifact_store`, `registry_conn`, `edition`, `page_filter`) |

---

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|-------|----------|
| Implement new stages against the `Stage` protocol only | Add a shared base class or inheritance hierarchy for stages |
| Import `runner.stage_context` from a stage when runtime data is needed | Import `runner.executor`/`runner.plan` from a stage |
| Add a one-line rationale comment next to any new `ignore_imports` entry | Add a cross-layer import without an explicit, reviewed exception |
| Route all artifact writes through `ArtifactStore` (content-addressed, atomic) | Write pipeline output artifacts with plain `Path.write_text`/`write_bytes` |

---

## Quick Reference

| Need | Location | Pattern |
|------|----------|---------|
| CLI entry point | `cli/main.py` | Typer `app` |
| Stage orchestration | `runner/executor.py`, `runner/plan.py` | cache-checked executor |
| Domain/stage logic | `stages/<name>/stage.py` | `Stage` protocol |
| Evaluation/QA harness | `eval/`, `stages/qa/` | invariant + rule runners |
| External services | `services/llm/`, `services/pdf/`, `services/assets/` | Protocol + Factory |
| Artifact persistence | `store/artifact_store.py`, `store/atomic_write.py` | content-addressed, atomic |
| Config | `config/loader.py`, `config/models.py` | layered TOML → Pydantic |

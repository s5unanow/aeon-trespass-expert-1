# Pipeline Architecture — apps/pipeline

**Project**: atr-pipeline (`apps/pipeline/pyproject.toml`)
**Style**: Layered, stage-oriented content compiler (PDF → IR → translate → QA → site bundle)
**Language**: Python 3.12 | **Stack**: pydantic + typer, uv workspace

## Architecture Overview

```
cli (typer commands)
  └─► runner (plan, executor, cache keys, stage context)
        └─► stages | eval          (13 stage packages; eval = golden-set harness)
              └─► services | store | registry   (llm/pdf/assets; artifacts; sqlite events)
                    └─► config     (TOML → pydantic models)
                          └─► utils (hashing)
```

Layer order is a hard contract enforced by import-linter — `pyproject.toml:91`
(`[tool.importlinter]`, "Pipeline layer contract" at `pyproject.toml:94`). A lower
layer never imports a higher one. Intentional exceptions (e.g. `stages.*.stage →
runner.stage_context` for the runtime context dataclass) are enumerated in
`ignore_imports` with per-line rationale comments — add new ones there, with a
comment, never by weakening the layers list.

## Stage Model

Every stage implements the `Stage` protocol — `runner/stage_protocol.py:13`:
`name`, `scope`, `version` properties plus `run(ctx, input_data) -> BaseModel`.
Stage order is data, not code: `WALKING_SKELETON_STAGES` at `runner/plan.py:6`
(ingest → extract_native → extract_layout → symbols → structure → translate →
style critic/repair → render → qa → chunk_export → publish); the EN-only variant
`SOURCE_ONLY_STAGES` at `runner/plan.py:22` skips translation. Partial runs slice
this list via `resolve_stage_range` (`runner/plan.py:35`).

Two packages sit outside the linear plan:

| Package | Role | Evidence |
|---|---|---|
| `stages/patch` | Applies `PatchSetV1` operations to artifact dicts (human corrections replayed onto IR) | `stages/patch/applicator.py:1` |
| `stages/assistant` | `ChunkExportStage` — exports `PageIRV1` pages as `RuleChunkV1` semantic chunks | `stages/assistant/stage.py:1` |

Stages receive a `StageContext` dataclass (`runner/stage_context.py:15`): run_id,
document_id, config, artifact_store, registry_conn, logger, edition, page_filter.
Stages take dependencies from the context — they never construct stores or open
registry connections themselves.

## Executor and Cache-Key Model

`execute_stage` (`runner/executor.py:23`) wraps every stage invocation:

1. Build a deterministic cache key — `build_cache_key` (`runner/cache_keys.py:8`)
   hashes stage name, `stage_v={stage_version}` (`runner/cache_keys.py:24`),
   schema version, config hash, and sorted input hashes.
2. Look up a completed event with the same key — `find_cached_event`
   (`registry/events.py:48`). On a hit, `run()` is skipped entirely and a
   `cached=True` result is returned.
3. On a miss, run the stage, persist the output via `put_json`
   (`runner/executor.py:102`), and record start/finish events in the registry.

Consequences:

| Avoid | Prefer |
|---|---|
| Adding a new artifact write to a stage's `run()` without bumping `version` | Bump `version` in the same PR + cache-hit regression test — see `.claude/rules/pipeline.md` § "Stage-output cache invalidation" and the bump-history comments at `stages/qa/stage.py:51` |
| Reading external inputs inside `run()` that the cache key can't see | Contribute them via `extra_cache_inputs` — `stages/ingest/stage.py:48` folds the source-PDF content hash into the key (S5U-1221) |
| Trusting a cached event blindly | The executor self-heals: `_cached_artifact_present` (`runner/executor.py:142`) re-runs the stage when the registry and artifact store diverge |

## Artifact Store (store/)

`ArtifactStore` (`store/artifact_store.py:30`) is the immutable, content-addressed
data plane: JSON at `document_id/schema_family/scope/entity_id/<content_hash>.json`.
`put_json` (`store/artifact_store.py:45`) dedupes on content hash; `put_bytes`
(`store/artifact_store.py:96`) handles binary rasters. "Latest" selection breaks
mtime ties deterministically by content-hash filename (`store/artifact_store.py:17`,
S5U-1229).

All disk writes go through `atomic_write_bytes` / `atomic_write_text`
(`store/atomic_write.py:11` / `:39`) — full-write loop + fsync + `os.replace`, so a
crash never exposes a truncated artifact. Never use plain `Path.write_text` for
artifact outputs (`.claude/rules/pipeline.md`).

## Registry (registry/)

SQLite event log, opened via `open_registry` (`registry/db.py:42`). Every stage
invocation records start/finish events (`record_stage_start`,
`registry/events.py:10`) with status `completed` / `cached` / `failed`, cache key,
and artifact ref — this is both the cache index and the provenance trail that
manifests are built from (`runner/manifest_builder.py`).

## Services

| Service | Purpose | Evidence |
|---|---|---|
| `services/llm` | Translation provider adapters behind `TranslatorAdapter` protocol (`base.py:33`); implementations include Mock, OpenAI, Anthropic, Gemini, and CLI adapters (gemini-cli, codex-cli, agy) | factory: `services/llm/factory.py:232` (`create_translator`) |
| `services/llm/fallback.py` | Retry-with-fallback across adapters, logging each failed attempt with `exc_info` | `services/llm/fallback.py:101` |
| `services/pdf` | Rasterization + image extraction (PyMuPDF) | `services/pdf/rasterizer.py:11` (`render_page_png`) |
| `services/assets` | Symbol/icon identity, resolution, and inline placement | `services/assets/resolver.py:30` |

To add a translation provider: implement the `TranslatorAdapter` protocol in
`services/llm/`, register it in `factory.py`, and see
`docs/specs/translation-providers.md` for the provider-switch contract.

## Configuration

TOML under `configs/` is loaded into pydantic models — `config/models.py:17`
(`DocumentConfig`) and siblings; validation happens at load time, not at use
sites. The config hash participates in every cache key, so config changes
invalidate downstream stages automatically.

## Boundaries Summary

| DO | DON'T |
|---|---|
| Implement the `Stage` protocol and let `execute_stage` own caching/eventing | Call another stage's `run()` directly |
| Persist through `ctx.artifact_store` | Write artifact files with `Path.write_text` |
| Add intentional cross-layer imports to `ignore_imports` with a rationale comment | Import `runner.executor`/`registry` orchestration from a stage |
| Bump `version` when `run()` gains an observable side-effect | Ship a new artifact write against an unchanged cache key |

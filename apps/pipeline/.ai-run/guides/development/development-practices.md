# Development Practices — apps/pipeline

**Language**: Python 3.12 | **Package manager**: uv (workspace member)
**Linter/Formatter**: ruff (root `pyproject.toml:35`) | **Types**: mypy strict (root `pyproject.toml:74`)

Authoritative conventions live in `.claude/rules/pipeline.md` and
`.claude/rules/hooks.md`; this guide maps them to concrete code.

## Code Quality Gates

| Action | Command | Config |
|---|---|---|
| Lint + everything else | `make lint` (repo root) | ruff select incl. `C901`, `PLR091x` — `pyproject.toml:41` |
| Format check / fix | `ruff format --check` via `make lint` / `make format` | line-length 100 — `pyproject.toml:37` |
| Types | `make typecheck` (`uv run mypy`, strict) | `pyproject.toml:74` |
| Aggregate before PR | `make check` | see CLAUDE.md |

Hard limits enforced mechanically:

- **McCabe complexity ≤ 12** — `pyproject.toml:43`. Per-file ignores exist only
  for grandfathered modules with a tracking issue (`pyproject.toml:51`).
- **≤ 400 lines per source/test file** — `scripts/check_file_length.py`;
  pre-existing violators are frozen in `KNOWN_VIOLATORS`
  (`scripts/check_file_length.py:41`) and must not grow. Split modules instead
  of appending to a near-cap file.
- **Import layers** — import-linter contract at root `pyproject.toml:94`; see
  the architecture guide for the layer order.

Always use toolchain wrappers (`uv run ruff`, `uv run mypy`, `uv run pytest`) —
bare tools fail here (`.claude/rules/hooks.md`).

## Logging

Default: stdlib `logging.getLogger(__name__)` at module top —
`stages/qa/auto_fix.py:53`. Prefer `structlog` only for **new** services that
need structured context fields; do not migrate existing stdlib code
(`.claude/rules/pipeline.md`).

| Avoid | Prefer |
|---|---|
| `print()` for diagnostics in pipeline code | Module logger; stage code can also use the injected `ctx.logger` (`runner/stage_context.py:15`) |
| `except Exception: pass` (bare swallow) | Log with exception context — retry loop at `services/llm/fallback.py:101` logs each failure with `exc_info=True` before retrying |

No bare `except Exception` without structured logging — AGENTS.md NEVER list.
The executor's catch-all (`runner/executor.py:125`) is the pattern for
"catch, record as a failed event, return an error result" rather than
swallowing.

## Data Models

pydantic for all data models and validation — config models at
`config/models.py:17` (`DocumentConfig` etc.); stage outputs are pydantic
models returned from `run()` (`runner/stage_protocol.py:25`) and serialized by
the executor. Cross-product schemas live in `packages/schemas/python/`
(`atr_schemas`) and flow Pydantic → JSON Schema → TS; never hand-edit the
generated outputs (`.claude/rules/schemas.md`).

| Avoid | Prefer |
|---|---|
| Dicts + ad-hoc validation at use sites | pydantic model with field validators — `config/models.py:17` |
| Defining a pipeline-output shape only in `apps/pipeline` | Add it to `atr_schemas` and run `make codegen` |

## Artifact IO — Atomic Writes Only

Artifact outputs must go through `atomic_write_bytes` / `atomic_write_text`
(`store/atomic_write.py:11` / `:39` — full-write loop, fsync, `os.replace`),
normally indirectly via `ArtifactStore.put_json`
(`store/artifact_store.py:76`). Plain `Path.write_text` on an artifact path can
expose a truncated file to a concurrent or crashed run
(`.claude/rules/pipeline.md`). Stdlib `json` is current practice; `orjson` is
not a dependency.

## Stage Version-Bump Rule

If a stage's `run()` gains any new observable side-effect (new
`put_json`/`put_binary` call, new `atomic_write_*`, new persisted record), bump
the stage's `version` property in the same PR and add a cache-hit regression
test — otherwise cached runs silently skip the new side-effect forever.
Authoritative rule + worked example: `.claude/rules/pipeline.md`
§ "Stage-output cache invalidation (S5U-662)".

House style for the bump: document each bump inline in the `version` property
with issue ID and rationale — see `stages/ingest/stage.py:30` (1.1 → 1.2,
cache-key composition change) and `stages/qa/stage.py:51` (bump history pointer
into the version test's docstring). Cache-key composition changes
(`extra_cache_inputs`, `stages/ingest/stage.py:48`) count as bump-worthy too.

## Text Concatenation Over Mixed Inlines

When flattening a sequence of mixed inline types (TextInline, IconInline, …),
skipped non-text inlines are word boundaries: join with `" "`, never
`"".join()` on the filtered subset (`.claude/rules/pipeline.md`). Example
consumer: symbol/inline placement in `services/assets/inline_placer.py`.

## Workflow Essentials

- Branch/commit/PR/review flow, red-before evidence, and coverage tables are
  defined in AGENTS.md ("Development workflow") — commits are prefixed with the
  Linear ID (`S5U-XXX:`).
- The pre-commit hook runs the local quality gates automatically; never bypass
  it without disclosure (`.claude/rules/hooks.md` § "Hook-bypass disclosure").
- Guard scripts and CI checks you add or touch must be fail-closed and
  content-derived — `.claude/rules/guards.md` Rules G1/G2.

## Quick Reference

| Need | Location |
|---|---|
| Lint/format/type config | root `pyproject.toml:35` onward |
| File-length gate | `scripts/check_file_length.py` |
| Atomic write helpers | `apps/pipeline/src/atr_pipeline/store/atomic_write.py` |
| Stage protocol + context | `apps/pipeline/src/atr_pipeline/runner/stage_protocol.py`, `runner/stage_context.py` |
| Config models | `apps/pipeline/src/atr_pipeline/config/models.py` |
| Hashing utilities | `apps/pipeline/src/atr_pipeline/utils/hashing.py` |

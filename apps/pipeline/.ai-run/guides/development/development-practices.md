# Development Practices — apps/pipeline

**Project**: atr-pipeline
**Language**: Python 3.12 | **Framework**: typer + pydantic (uv workspace)
**Linter**: ruff | **Formatter**: ruff format | **Type checker**: mypy --strict

`.claude/rules/pipeline.md` and `.claude/rules/hooks.md` are the authoritative
convention sources; this guide summarizes them with codebase evidence.

---

## Code Quality

### Commands (always via toolchain wrappers — bare tools fail in this repo)

| Action | Command | Auto-fix |
|--------|---------|----------|
| Lint | `uv run ruff check .` | `uv run ruff check --fix .` |
| Format check | `uv run ruff format --check .` | `make format` |
| Type check | `uv run mypy apps/pipeline/src packages/schemas/python` (`Makefile:13`) | - |
| Import layers | `uv run lint-imports` | - |
| File length | `uv run python scripts/check_file_length.py` | - |
| All local gates | `make check` (lint + typecheck + test) | - |

### Configuration (root `pyproject.toml`)

| Rule | Setting | Source |
|------|---------|--------|
| Line length 100, py312 | `[tool.ruff]` | root `pyproject.toml:35-37` |
| McCabe complexity max 12 | `C901` selected; `max-complexity = 12` | root `pyproject.toml:41,43-44` |
| mypy strict | `strict = true` | root `pyproject.toml:74-76` |
| 400-line cap per source/test file | `--max` default 400; pre-existing violators grandfathered in `KNOWN_VIOLATORS` and must not grow | `scripts/check_file_length.py:41,109` |
| Complexity grandfathers | per-file-ignores (do not extend casually) | root `pyproject.toml:51-55` |

Pre-commit hook (`.claude/hooks/pre-commit-check.sh`) runs all of the above
plus the fast pytest subset on every `git commit`.

---

## Data Modeling — pydantic everywhere

All data models and validation use pydantic; stage IO is typed as `BaseModel`.

| Avoid | Prefer |
|---|---|
| Dicts / dataclasses for pipeline data | `BaseModel` config models — `apps/pipeline/src/atr_pipeline/config/models.py:17` |
| Untyped stage IO | `run(ctx, input_data: BaseModel | None) -> BaseModel` — `apps/pipeline/src/atr_pipeline/runner/stage_protocol.py:25` |
| Hand-written TS types for these models | Codegen chain Pydantic → JSON Schema → TS (`.claude/rules/schemas.md`; `make codegen`) |

---

## Logging

Stdlib `logging.getLogger(__name__)` is the module-level default; prefer
`structlog` only for **new** services needing structured context fields — do
not migrate existing code (`.claude/rules/pipeline.md`). Never `print()` for
diagnostics in pipeline code.

| Avoid | Prefer |
|---|---|
| `print("skipping fixer")` | `logger.warning("Unknown fixer %s in %s", ...)` — `apps/pipeline/src/atr_pipeline/stages/qa/auto_fix.py:53,136` |
| Migrating stdlib logging to structlog "for the rule" | Keep stdlib logging in existing modules; structlog for new structured services only |
| Logging without context | %-style args carrying stage name / cache key — `apps/pipeline/src/atr_pipeline/runner/executor.py:60` |

---

## Error Handling

No bare `except Exception` without logging the exception context.

| Avoid | Prefer |
|---|---|
| `except Exception: pass` | Log then re-raise/record — retry loop logs each attempt: `apps/pipeline/src/atr_pipeline/services/llm/fallback.py:101-104` |
| Swallowing stage failures | Executor records `status="failed"` + error message in the registry — `apps/pipeline/src/atr_pipeline/runner/executor.py:125-133` |
| Broad suppress as control flow | `contextlib.suppress(OSError)` only for narrow, commented cleanup — `apps/pipeline/src/atr_pipeline/store/atomic_write.py:32` |

---

## Artifact IO — atomic writes only

JSON IO uses stdlib `json` (orjson is not a dependency). Artifact outputs MUST
go through `atr_pipeline.store.atomic_write` (temp file + `fsync` +
`os.replace`) — never plain `Path.write_text` / `write_bytes`.

| Avoid | Prefer |
|---|---|
| `path.write_text(json.dumps(data))` for artifacts | `atomic_write_text` / `atomic_write_bytes` — `apps/pipeline/src/atr_pipeline/store/atomic_write.py:11,39` |
| Direct file writes from a stage | `ctx.artifact_store.put_json(...)` (content-addressed, dedups, atomic) — `apps/pipeline/src/atr_pipeline/store/artifact_store.py:45,76` |

---

## Mixed-Inline Text Concatenation

When concatenating text from a sequence of mixed inline types (`TextInline`,
`IconInline`, …), skipped non-text inlines represent word boundaries — join the
filtered text nodes with `" "`, never `"".join()` on the filtered subset alone
(`.claude/rules/pipeline.md`).

| Avoid | Prefer |
|---|---|
| `"".join(n.text for n in inline if isinstance(n, TextInline))` | `" ".join(node.text for node in inline if isinstance(node, TextInline))` — `apps/pipeline/src/atr_pipeline/stages/translation/grouping.py:112` |

(`"".join` is only valid when the parts list was built without filtering out
boundary-bearing nodes — e.g. `grouping.py:43` concatenates consecutive
`TextInline` runs that stop at the first marker.)

---

## Stage Version Bump Rule (S5U-662)

If a stage's `run()` gains a new artifact write (`put_json` / `put_binary` /
`atomic_write_*`), persisted record, or any new observable side-effect, bump
the stage class's `version` in the same PR **and** add a cache-hit regression
test — otherwise cached runs silently omit the new side-effect.

- Rule + worked test example: `.claude/rules/pipeline.md` § "Stage-output
  cache invalidation".
- Why: cache key embeds `stage_v={stage_version}` —
  `apps/pipeline/src/atr_pipeline/runner/cache_keys.py:25`.
- Bump-comment convention with per-bump rationale:
  `apps/pipeline/src/atr_pipeline/stages/qa/stage.py:51-61`.
- Test shape: see `apps/pipeline/.ai-run/guides/testing/testing-patterns.md`
  § "Cache-Hit Regression Test".

---

## Git Workflow (short form — CLAUDE.md is authoritative)

- Branch: `s5unanow/s5u-XXX-short-description`; never commit directly to main.
- Commit prefix: `<linear-id>: description` (e.g. `S5U-724:`).
- New tests require red-before evidence (`.claude/rules/hooks.md` § "Three-input
  test discipline"); never skip pre-commit hooks without disclosure.
- Local green (`make check`) permits push; merge requires CI green.

---

## Don't Do

| ❌ Avoid | ✅ Instead | Why |
|----------|-----------|-----|
| `print()` diagnostics | `logging.getLogger(__name__)` | Pipeline output must be log-managed |
| `Path.write_text` for artifacts | `atomic_write_*` / `ArtifactStore` | Partial writes must never become visible |
| Bare `except Exception` silently | Log context, record failure | Debuggability; NEVER-list rule |
| New side-effect, unchanged `version` | Bump + cache-hit test | Cached runs silently drop the side-effect |
| Files > 400 lines | Split module | `scripts/check_file_length.py` gate |
| Manual TS types for models | `make codegen` | Pydantic is the contract source |

## Quick Reference

| Need | Location |
|------|----------|
| Lint/format/mypy/import-linter config | root `pyproject.toml:35-132` |
| Pre-commit gate script | `.claude/hooks/pre-commit-check.sh` |
| Atomic write helpers | `apps/pipeline/src/atr_pipeline/store/atomic_write.py` |
| Config models + loader | `apps/pipeline/src/atr_pipeline/config/` |
| Authoritative conventions | `.claude/rules/pipeline.md`, `.claude/rules/hooks.md`, `.claude/rules/schemas.md` |

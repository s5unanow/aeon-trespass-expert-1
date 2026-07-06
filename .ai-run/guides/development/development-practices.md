# Development Practices

Conventions for writing pipeline (Python) and reader (TypeScript) code in this repo.
Path-scoped detail lives in `.claude/rules/` (auto-loaded on file match) — this guide is
the index and the cross-cutting rules.

## Python (apps/pipeline)

### Data modeling & validation
State the rule: all data models and validation use Pydantic; the IR is the canonical
state, not Markdown.

| Avoid | Prefer |
|---|---|
| Ad-hoc dicts passed between stages | Pydantic models in `packages/schemas/python/` |
| Hand-writing TS types to match Python | Regenerate via `make codegen` (`.claude/rules/schemas.md`) |

### Artifact IO — always atomic
Never write pipeline artifacts with plain `Path.write_text` / `write_bytes`. Use the
temp-file + `os.replace` helpers so a crash can't leave a torn file.

| Avoid | Prefer |
|---|---|
| `path.write_bytes(data)` for an artifact | `atomic_write_bytes(path, data)` — `apps/pipeline/src/atr_pipeline/store/atomic_write.py:11` |
| `path.write_text(s)` for an artifact | `atomic_write_text(path, s)` — `atomic_write.py:39` |

### Stage-output cache invalidation
When a stage's `run()` gains a new observable side-effect (new `put_json`/`put_binary`,
new `atomic_write_*`, new persisted record), bump that stage class's `version` in the same
PR and add a cache-hit regression test. The executor cache key includes `stage_v`
(`runner/cache_keys.py:8`); an unchanged version makes cached runs silently skip the new
write. Full worked example: `.claude/rules/pipeline.md` (S5U-662).

### Logging & errors
| Avoid | Prefer |
|---|---|
| `print()` for diagnostics | stdlib `logging.getLogger(__name__)` (default); `structlog` for new structured services |
| Bare `except Exception:` | Catch narrowly and log the exception context (`.claude/rules/pipeline.md`) |

### Text from mixed inlines
When concatenating a sequence of mixed inline types (TextInline, IconInline…), non-text
inlines are word boundaries — join with `" "`, never `"".join()` on the filtered subset.

## TypeScript (apps/web)

- React 19 + Vite 6 + React Router 7 (`apps/web/package.json`).
- Types are **generated** from Pydantic → JSONSchema → TS; never hand-author files under
  `packages/schemas/ts/` (`.claude/rules/web.md`, `.claude/rules/schemas.md`).
- Components are focused / single-responsibility; no import cycles
  (`import/no-cycle: error`, `apps/web/.oxlintrc.json`).

| Avoid | Prefer |
|---|---|
| Manual `interface Foo` mirroring a model | Import the generated type; change the Pydantic source + `make codegen` |
| Circular component imports | Break the cycle (oxlint blocks it) |

## File size

Max 400 lines per source and test file, enforced by `check_file_length.py` (Python) and
oxlint `max-lines: 400` (`apps/web/.oxlintrc.json`). Pre-existing violators are
grandfathered and must not grow.

## Path-scoped rule index

| Area | Rule file |
|---|---|
| Pipeline (logging, IO, cache invalidation) | `.claude/rules/pipeline.md` |
| Web (React/Vite/oxlint) | `.claude/rules/web.md` |
| Schemas (codegen direction) | `.claude/rules/schemas.md` |
| Extraction work | `.claude/rules/extraction.md`, `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` |
| Hooks / shell gating | `.claude/rules/hooks.md` |
| CI guard discipline | `.claude/rules/guards.md` |
| Visual verification | `.claude/rules/visual-verify.md` |

## Do / Don't

| ✅ DO | ❌ DON'T |
|---|---|
| Edit Pydantic models then `make codegen` | Edit generated `jsonschema/` or `ts/` by hand |
| Write artifacts atomically via `store` | Use raw `Path.write_*` for artifact output |
| Keep files ≤ 400 lines | Grow a grandfathered violator |
| Bump stage `version` on new side-effects | Ship a new artifact write with an unchanged version |

# Schema Codegen Contract — packages/schemas

**Project**: atr-schemas (`packages/schemas/python/pyproject.toml`) / `@atr/schemas` (`packages/schemas/ts/package.json`)
**Contract direction**: Python Pydantic → JSON Schema → TypeScript — one-way, never reversed
**Authoritative rule**: `.claude/rules/schemas.md` — this guide summarizes it; on conflict, the rule file wins.

---

## Contract Direction

Pydantic v2 models under `packages/schemas/python/atr_schemas/` are the single
source of truth. Everything downstream is generated:

| Layer | Path | Status | Producer |
|---|---|---|---|
| Pydantic models | `packages/schemas/python/atr_schemas/*.py` | **Hand-written** | you |
| JSON Schema | `packages/schemas/jsonschema/*.schema.json` | Generated — never edit | `scripts/generate_jsonschema.py:100-107` |
| TS types | `packages/schemas/ts/src/generated/*.ts` | Generated — never edit | `scripts/generate_ts_types.mjs:56-77` |
| TS barrel | `packages/schemas/ts/src/index.ts` | Generated — never edit | `scripts/generate_ts_types.mjs:79-89` |

Each generated file carries a banner (`/* Auto-generated from JSON Schema — do
not edit */`, see `packages/schemas/ts/src/generated/page_ir_v1.ts:1` and
`packages/schemas/ts/src/index.ts:1`). Manual TypeScript types for schema data
are forbidden repo-wide (`.claude/rules/web.md`).

The Python package is consumed directly by the pipeline as a uv workspace
member (`pyproject.toml:18` — `atr-schemas = { workspace = true }`); models
import shared primitives from `atr_schemas/common.py:11` (`Rect`) and enums
from `atr_schemas/enums.py`.

## Change Flow

Any Pydantic model change follows one loop:

1. Edit the model in `packages/schemas/python/atr_schemas/<name>.py`
   (e.g. `page_ir_v1.py:15-22` `TextInline`).
2. `make codegen` (`Makefile:57-59`) — runs
   `uv run python scripts/generate_jsonschema.py` then
   `node scripts/generate_ts_types.mjs`.
3. Commit the model edit **and** the regenerated
   `packages/schemas/jsonschema/` + `packages/schemas/ts/src/` diff together
   in the same commit — CI diffs generated output against a fresh regeneration.

### Adding a new schema

1. Create `packages/schemas/python/atr_schemas/<snake_name>_v1.py` with a root
   `BaseModel` (give the class a real name — it becomes the JSON Schema `title`
   and the exported TS type name).
2. Register it in the `MODELS` dict in `scripts/generate_jsonschema.py:54-95`
   — this dict is the explicit list of what gets generated (40 schemas today).
3. `make codegen`. The TS side needs no registration: it globs
   `*.schema.json` (`scripts/generate_ts_types.mjs:48`) and derives the
   exported type name from the schema `title`
   (`derivePrimaryType`, `scripts/generate_ts_types.mjs:33-43`). A schema with
   no usable `title` **throws** — fail loud, no silent skips (S5U-1234).
4. Commit model + registration + all generated files together.

## Freshness Gate

`scripts/check_codegen_fresh.sh` regenerates both layers and fails on any
resulting `git diff` (`scripts/check_codegen_fresh.sh:7-16`). It runs in three
places:

| Surface | Wiring |
|---|---|
| `make lint` (and via it `make check`) | `Makefile:19` |
| `make check-codegen` | `Makefile:52-55` (preflights that node + pnpm packages exist) |
| CI `python / test` job | `.github/workflows/python-tests.yml:82-83` |

The gate is content-derived: it does not trust file timestamps or commit
messages — it re-runs codegen and compares bytes. A stale commit therefore
cannot merge (`python / test` is a required check).

## Bad vs Best Practice

| ❌ Avoid | ✅ Instead | Why |
|---|---|---|
| Editing `packages/schemas/ts/src/generated/*.ts` or `index.ts` by hand | Edit the Pydantic model, run `make codegen` | Next regeneration silently reverts your edit; freshness gate fails CI either way |
| Editing `packages/schemas/jsonschema/*.schema.json` directly | Same — change the Pydantic source | Same file is overwritten by `scripts/generate_jsonschema.py:100-107` |
| Writing a manual TS interface in `apps/web` for bundle data | Import from `@atr/schemas` (see consumers below) | Duplicated shape drifts from the Pydantic contract with no gate |
| Committing a model change without the regenerated output | Run `make codegen` and commit the full diff in one commit | `check_codegen_fresh.sh` fails `make lint` and CI |
| Adding a model file but forgetting the `MODELS` entry | Register in `scripts/generate_jsonschema.py:54-95` | Unregistered models generate nothing — the contract never reaches TS |

## How apps/web Consumes @atr/schemas

`@atr/schemas` is a private workspace package
(`packages/schemas/ts/package.json` — `"main": "./src/index.ts"`), declared in
`apps/web/package.json:26` as `"@atr/schemas": "workspace:*"`. The generated
barrel offers two import styles:

| Style | Use for | Example |
|---|---|---|
| Direct type export | The root type of a schema | `import type { QAMetricsV1 } from '@atr/schemas'` — `apps/web/src/components/nav/QaMetricsCards.tsx:1` |
| Namespace export (`camelCaseV1`) | Nested/inner types of a schema | `import type { renderPageV1 } from '@atr/schemas'` — `apps/web/src/lib/render/types.ts:22` |

Both styles may be mixed in one import
(`apps/web/src/lib/feedback/schema.ts:12`). Always `import type` — the package
ships types only; `tsc --noEmit` is its lint and typecheck script
(`packages/schemas/ts/package.json`).

## Quick Reference

| Need | Location |
|---|---|
| Pydantic sources | `packages/schemas/python/atr_schemas/` |
| Schema registration | `scripts/generate_jsonschema.py:54` (`MODELS`) |
| Regenerate | `make codegen` (`Makefile:57`) |
| Verify freshness | `make check-codegen` (`Makefile:52`) |
| Freshness gate script | `scripts/check_codegen_fresh.sh` |
| Authoritative rule | `.claude/rules/schemas.md` |

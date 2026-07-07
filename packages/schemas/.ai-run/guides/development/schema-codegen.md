# Schema Codegen — packages/schemas

The shared-schema bridge between the Python pipeline and the TypeScript web
reader. One direction only: **Pydantic → JSON Schema → TypeScript**. The
authoritative short-form rule is `.claude/rules/schemas.md:6-8`; this guide is
the workflow detail.

## Contract direction

Python Pydantic models are the single source of truth. Everything downstream
is generated:

| Layer | Path | Status |
|---|---|---|
| Source of truth | `packages/schemas/python/atr_schemas/*.py` | Hand-written Pydantic v2 models |
| Generated | `packages/schemas/jsonschema/*.schema.json` | Output of `scripts/generate_jsonschema.py` |
| Generated | `packages/schemas/ts/src/generated/*.ts` + `ts/src/index.ts` | Output of `scripts/generate_ts_types.mjs` |

Never hand-edit the generated layers — both generators stamp a
"do not edit" banner (`scripts/generate_ts_types.mjs:64`,
`scripts/generate_jsonschema.py:5`), and `packages/schemas/ts/src/index.ts:1`
is an auto-generated barrel. Never write manual TS types for schema data
anywhere in `apps/web` (see AGENTS.md NEVER list).

## How to regenerate

After any change to a Pydantic model under `packages/schemas/python/atr_schemas/`:

```bash
make codegen
```

This runs the two generators in order (`Makefile:57-59`):

1. `uv run python scripts/generate_jsonschema.py` — emits one
   `<name>.schema.json` per entry in the `MODELS` map
   (`scripts/generate_jsonschema.py:54`).
2. `node scripts/generate_ts_types.mjs` — compiles each schema via
   `json-schema-to-typescript` and rebuilds the barrel with namespace +
   direct type exports (`scripts/generate_ts_types.mjs:74-76`). The primary
   export name is content-derived from the schema `title`; a schema without a
   usable title fails loud (`scripts/generate_ts_types.mjs:33-43`).

Commit the regenerated JSON Schema and TS output together with the model change.

## Adding a new schema

1. Create the model in `packages/schemas/python/atr_schemas/<name>_v1.py`
   (reuse primitives from `atr_schemas/common.py:11` — `Rect`,
   `PageDimensions`, `ProvenanceRef`).
2. Register it in the `MODELS` map in `scripts/generate_jsonschema.py:54`
   (import + dict entry, alphabetical).
3. `make codegen`, then commit model + generated files in one commit.

The TS side needs no registration — `generate_ts_types.mjs:48` globs every
`*.schema.json` in the directory.

## Freshness verification

`scripts/check_codegen_fresh.sh:6-16` re-runs both generators and fails if
`git diff` is non-empty over `packages/schemas/jsonschema` and
`packages/schemas/ts/src`. It runs in three places:

- `make check-codegen` — standalone, with node/pnpm preflight (`Makefile:52-55`)
- `make lint` — part of the aggregate lint target (`Makefile:19`)
- CI — `.github/workflows/python-tests.yml:83` on every push/PR

So a model change committed without its regenerated output fails CI. The fix
is always `make codegen` + commit, never editing the generated files to match.

## Consumers

- **apps/pipeline** depends on the Python package `atr-schemas` as a uv
  workspace member (`apps/pipeline/pyproject.toml:29`, workspace root
  `pyproject.toml:13`). Example: `apps/pipeline/src/atr_pipeline/stages/assistant/chunker.py:10`
  imports `from atr_schemas.common import NormRect, Rect`.
- **apps/web** depends on `@atr/schemas` as a pnpm workspace dep
  (`apps/web/package.json:26`, package defined at
  `packages/schemas/ts/package.json:2`). Example:
  `apps/web/src/lib/api/loadGlossary.ts:1` imports
  `import type { GlossaryPayloadV1 } from '@atr/schemas'`.

## Bad vs best

| Avoid | Prefer |
|---|---|
| Hand-editing `packages/schemas/ts/src/generated/*.ts` or `index.ts` | Edit the Pydantic model, then `make codegen` |
| Hand-editing `packages/schemas/jsonschema/*.schema.json` | Same — the JSON Schema is generated output |
| Writing a local `interface` in `apps/web` for schema-shaped data | Import the generated type from `@atr/schemas` (`apps/web/src/lib/api/loadGlossary.ts:1`) |
| Adding a model but skipping the `MODELS` registration | Register in `scripts/generate_jsonschema.py:54` — unregistered models silently produce no schema |
| Committing a model change without regenerated output | `make codegen` in the same commit; `check_codegen_fresh.sh` fails CI otherwise |

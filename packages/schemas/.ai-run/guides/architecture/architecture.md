# Architecture — packages/schemas

**Style**: One-way codegen pipeline, not an app. A single Pydantic source of
truth fans out to two generated artifacts consumed by the other two modules
in the monorepo.

**Key decision**: hand-write types once (Python), generate everywhere else,
so `apps/pipeline` and `apps/web` can never drift into incompatible shapes
for the same wire format.

## Pipeline Overview

```
packages/schemas/python/atr_schemas/*.py   (hand-authored Pydantic v2 models)
              │  scripts/generate_jsonschema.py
              ▼
packages/schemas/jsonschema/*.schema.json  (generated)
              │  scripts/generate_ts_types.mjs
              ▼
packages/schemas/ts/src/generated/*.ts     (generated)
packages/schemas/ts/src/index.ts           (generated barrel)
              │
              ▼
apps/web (imports "@atr/schemas")
```

`apps/pipeline` skips the generated artifacts entirely and imports
`atr_schemas` (the Python package) directly — see Consumers below.

## Component Structure

| Path | Role |
|---|---|
| `packages/schemas/python/atr_schemas/*.py` | Source of truth — Pydantic v2 models, e.g. `PageIRV1` at `packages/schemas/python/atr_schemas/page_ir_v1.py:341` |
| `packages/schemas/python/atr_schemas/__init__.py` | Hand-maintained barrel; every model must be exported here (`__all__`, `packages/schemas/python/atr_schemas/__init__.py:135-274`) |
| `packages/schemas/jsonschema/*.schema.json` | Generated JSON Schema, one file per registered model |
| `packages/schemas/ts/src/generated/*.ts` | Generated TS types, one file per schema |
| `packages/schemas/ts/src/index.ts` | Generated barrel re-exporting every schema's types to `@atr/schemas` consumers |

## Generation Stages

1. **Author** — add/modify a Pydantic model under `atr_schemas/`, export it from `__init__.py`.
2. **Register (JSON Schema stage only)** — add the model to the `MODELS` dict in `scripts/generate_jsonschema.py:54-95`; `generate()` (`scripts/generate_jsonschema.py:100-107`) calls `model.model_json_schema()` per entry and writes `packages/schemas/jsonschema/<name>.schema.json`.
3. **TS stage is auto-discovered, not registered** — `scripts/generate_ts_types.mjs:48` reads every `*.schema.json` in the schema dir (no allowlist), derives the exported type name from each schema's `title` field via `derivePrimaryType` (`scripts/generate_ts_types.mjs:33-43`, throws rather than silently skipping a titleless schema — S5U-1234), compiles with `json-schema-to-typescript` (`scripts/generate_ts_types.mjs:63-67`), and regenerates `ts/src/index.ts`.
4. Both stages run together via `make codegen` (`Makefile:57-59`).

## Boundary Rule: Generated Dirs Are Never Hand-Edited

`packages/schemas/jsonschema/**` and `packages/schemas/ts/src/generated/**`
(+ `ts/src/index.ts`) carry `// Auto-generated ... do not edit` banners
(`packages/schemas/ts/src/generated/page_ir_v1.ts:1`,
`packages/schemas/ts/src/index.ts:1`). This is mechanically enforced, not
just documented: `scripts/check_codegen_fresh.sh:6-16` reruns both generators
and `git diff --quiet`s the two output directories, exiting 1 on drift. It is
wired into `make lint` (`Makefile:19`) and `make check-codegen`
(`Makefile:52-55`), so a hand-edit to a generated file is overwritten and
flagged the next time codegen runs.

## Consumers

| Consumer | Artifact | Wiring | Example import |
|---|---|---|---|
| `apps/pipeline` (Python) | `packages/schemas/python` directly — no generated intermediary | uv workspace member (`pyproject.toml:11-13,18`), dependency (`apps/pipeline/pyproject.toml:7,29`) | `from atr_schemas.page_ir_v1 import ...` — `apps/pipeline/src/atr_pipeline/stages/assistant/chunker.py:10-11` |
| `apps/web` (TypeScript) | `packages/schemas/ts` generated package (`@atr/schemas`) | pnpm workspace member (`pnpm-workspace.yaml:1-3`), dependency `"@atr/schemas": "workspace:*"` (`apps/web/package.json:26`) | `import type { renderPageV1 } from '@atr/schemas'` — `apps/web/src/lib/render/types.ts:22` |

## Enforced Workflow

- `make codegen` (`Makefile:57-59`) — regenerate JSON Schema + TS types from the Pydantic sources. Run after any model change.
- `make check-codegen` / `make lint` (`Makefile:19,52-55`) — fail if the regenerated output differs from what's committed. This freshness check is the only gate; there is no separate runtime schema-validation step.

## Adding a New Schema

1. Create `packages/schemas/python/atr_schemas/<name>_v1.py`; export the model from `__init__.py`.
2. Register it in the `MODELS` dict, `scripts/generate_jsonschema.py:54-95` (the TS stage needs no registration — step 3 in Generation Stages above).
3. Run `make codegen`; commit the new model together with its generated `jsonschema/<name>.schema.json`, `ts/src/generated/<name>.ts`, and the regenerated `ts/src/index.ts` in the same PR.

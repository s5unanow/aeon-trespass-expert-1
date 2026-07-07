# Schemas & Codegen Contract

**Rule of the road**: types flow **one way** — Pydantic → JSON Schema → TypeScript. Every shared data shape is defined once as a Pydantic model; the JSON Schema and TS types are generated. Never hand-write the downstream artifacts (`docs/adrs/ADR-011-shared-schemas-generated-to-jsonschema-and-ts.md`, `.claude/rules/schemas.md`).

## The Pipeline

```
packages/schemas/python/atr_schemas/*.py   (Pydantic — the source of truth)
        │  scripts/generate_jsonschema.py
        ▼
packages/schemas/jsonschema/*.schema.json   (generated)
        │  scripts/generate_ts_types.mjs
        ▼
packages/schemas/ts/src/generated/*.ts       (generated) ──► re-exported by packages/schemas/ts/src/index.ts
```

Regenerate both steps with one command: `make codegen` (`Makefile` `codegen:` target runs `generate_jsonschema.py` then `generate_ts_types.mjs`).

## Where Each Layer Lives

| Layer | Path | Editable? | Evidence |
|---|---|---|---|
| Pydantic models | `packages/schemas/python/atr_schemas/` (e.g. `glossary_payload_v1.py`) | ✅ edit here | `packages/schemas/python/atr_schemas/qa_summary_v1.py` |
| JSON Schema | `packages/schemas/jsonschema/*.schema.json` | ❌ generated | `scripts/generate_ts_types.mjs:5` names it as input |
| TypeScript types | `packages/schemas/ts/src/generated/*.ts` | ❌ generated | `scripts/generate_ts_types.mjs:6` "do not edit by hand" |
| TS re-export barrel | `packages/schemas/ts/src/index.ts` | ✅ (barrel only) | `packages/schemas/ts/src/index.ts` |

## Conventions

| ✅ DO | ❌ DON'T |
|---|---|
| Add/change a model in `packages/schemas/python/atr_schemas/`, then `make codegen` | Edit `packages/schemas/{jsonschema,ts}/` directly |
| Version schemas by filename suffix (`*_v1`) | Break an existing `_v1` shape in place |
| Consume generated types in `apps/web` via `@atr/schemas` (workspace dep) | Declare local mirror interfaces in the web app |
| Commit the regenerated files in the same PR as the model change | Leave codegen stale (CI blocks on it) |

## Freshness Gate

Generated output must match the Pydantic sources or CI fails. Verify locally before pushing:

- `make check-codegen` — checks generated schemas match sources (runs `scripts/check_codegen_fresh.sh`).
- The freshness check is CI gate #9 (`.github/workflows/`, enumerated in `CLAUDE.md` quality-gates section).

## Quick Reference

| Need | Command / Location |
|---|---|
| Regenerate all schemas + types | `make codegen` |
| Verify generated == source | `make check-codegen` |
| Add a new shared shape | new `*_v1.py` in `packages/schemas/python/atr_schemas/`, then `make codegen` |
| Import a type in web | `import { … } from '@atr/schemas'` |

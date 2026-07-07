# Architecture Guide — System Overview

**Project**: aeon-trespass-expert
**Style**: IR-first modular monolith + static reader (two-product monorepo)
**Stack**: Python 3.12 pipeline · React 19 / Vite web · shared Pydantic→JSON Schema→TS schemas

Deep detail lives in `docs/PROJECT_ARCHITECTURE.md` (read on demand — it is ~3,400 lines) and the 13 ADRs under `docs/adrs/`. This guide is the map; those are the territory. Module-specific guides: `architecture/pipeline.md`, `architecture/web.md`, `architecture/schemas-codegen.md`.

## Architecture Overview

The system compiles the Aeon Trespass rulebook PDF into a typed, immutable intermediate representation (IR), translates it EN→RU on structured units, runs release-blocking QA, and exports a static bundle that a React reader renders. Markdown is an export/debug format only — never the source of truth (`docs/adrs/ADR-002-markdown-not-source-of-truth.md`).

```
PDF ──► extract (native + layout) ──► symbols ──► structure ──► IR
                                                                 │
                                          translate (EN→RU) ◄────┘
                                                 │
                                          render ──► QA (release gate) ──► publish
                                                                              │
                              apps/web (React static reader) ◄─── site bundle ┘
```

**Key decision**: IR-first, not markdown-first — attacks icon loss, reading-order corruption, term drift, and idempotency bugs at the root (`docs/PROJECT_ARCHITECTURE.md:13`, `docs/adrs/ADR-001-ir-first-canonical-state.md`).

## Component Structure

```
apps/pipeline/       Python compiler: PDF -> IR -> translate -> QA -> bundle   (see architecture/pipeline.md)
apps/web/            React 19 / Vite static reader                              (see architecture/web.md)
packages/schemas/    python/ (Pydantic) -> jsonschema/ -> ts/ (generated)       (see architecture/schemas-codegen.md)
configs/             TOML: documents, base, ci, glossary, symbols
scripts/             Codegen, export, and 30+ CI guard scripts (check_*.py)
docs/                Architecture + 13 ADRs + specs (read on demand)
artifacts/           Pipeline output (gitignored run data)
```

## Core Architectural Rules

| Rule | Rationale | Evidence |
|---|---|---|
| Every stage output is immutable + content-addressed; corrections are typed patches, never in-place edits | Idempotency + provenance | `docs/adrs/ADR-003-immutable-artifacts-and-patches.md` |
| Contract direction is one-way: Pydantic → JSON Schema → TypeScript | Single source of truth for types | `docs/adrs/ADR-011-shared-schemas-generated-to-jsonschema-and-ts.md`, `.claude/rules/schemas.md` |
| QA is release-blocking, not advisory | Prevent silent quality regressions | `docs/adrs/ADR-010-qa-is-release-blocking.md` |
| Web renders typed nodes, not markdown | Preserve icons/structure end-to-end | `docs/adrs/ADR-008-static-react-reader.md` |
| No workflow orchestrator in v1 — a plain executor drives stages | Simplicity | `docs/adrs/ADR-009-no-workflow-orchestrator-v1.md` |

## Cross-Cutting Boundaries

| ✅ DO | ❌ DON'T |
|---|---|
| Change a schema in `packages/schemas/python/` then run `make codegen` | Hand-edit `packages/schemas/{jsonschema,ts}/` (generated) |
| Bump a stage's `version` field when adding a new artifact write | Add a `put_json`/`atomic_write_*` side-effect with an unchanged version (silent cache miss — `.claude/rules/pipeline.md`) |
| Use atomic writes (`store/atomic_write.py`) for artifact output | Use plain `Path.write_text`/`write_bytes` for artifacts |
| Rely on path-triggered `.claude/rules/*.md` for a one-file fix | Front-load the 3,400-line architecture doc on routine work |

## Adding a New Capability

- **New pipeline stage** → follow `architecture/pipeline.md` (stage protocol + executor + version field + cache-hit regression test).
- **New rendered block type** → add the Pydantic model, `make codegen`, then extend the exhaustive `switch`/`never` renderer in `apps/web` (see `architecture/web.md`).
- **New architecture decision** → draft an ADR under `docs/adrs/` and read `docs/PROJECT_ARCHITECTURE.md` first.

## Quick Reference

| Need | Location |
|---|---|
| System design (deep) | `docs/PROJECT_ARCHITECTURE.md`, `docs/PROJECT_ARCHITECTURE_TO_AGENTIC.md` |
| Decision records | `docs/adrs/ADR-001..013` |
| Pipeline internals | `architecture/pipeline.md`, `.claude/rules/pipeline.md` |
| Web internals | `architecture/web.md`, `.claude/rules/web.md` |
| Schema/codegen contract | `architecture/schemas-codegen.md`, `.claude/rules/schemas.md` |
| Extraction process | `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`, `.claude/rules/extraction.md` |

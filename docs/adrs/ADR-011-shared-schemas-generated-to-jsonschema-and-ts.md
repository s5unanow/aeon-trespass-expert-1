# ADR-011: Shared Schemas Generated to JSON Schema and TypeScript

**Status:** Accepted
**Date:** 2026-03-15

## Context
The pipeline (Python) and the reader (TypeScript/React) both consume the same data structures (e.g., `RenderPageV1`). Manually maintaining parallel type definitions invites drift. We need a single source of truth for shared schemas with automated generation for each consumer language.

## Decision
Python Pydantic models are the canonical schema definitions. JSON Schema files are generated from them via `pydantic.schema()`, and TypeScript types are generated from the JSON Schema using a code-generation tool (e.g., `json-schema-to-typescript`). Generated files are checked into the repo and regenerated in CI.

## Consequences
- Schema changes are made in one place (Python models) and propagated automatically.
- CI fails if generated files are stale, preventing accidental drift.
- The TypeScript reader gets compile-time type safety against the pipeline's output format.
- Adding a new consumer language requires only a new generator, not a new source of truth.

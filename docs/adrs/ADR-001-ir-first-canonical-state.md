# ADR-001: IR-First Canonical State

**Status:** Accepted
**Date:** 2026-03-15

## Context
The pipeline produces structured data at every stage (extraction, symbol recovery, translation, etc.). We need a single authoritative representation that all downstream stages and the reader consume. Relying on a loosely-typed format like markdown would force every consumer to re-parse prose and guess at semantics.

## Decision
The canonical state of every page is a typed intermediate representation (IR) defined as versioned Pydantic models. Markdown is generated only as a debug/export artifact and is never read back into the pipeline.

## Consequences
- All stage-to-stage contracts are expressed as typed Python dataclasses/Pydantic models with explicit versioning.
- Tools that need human-readable output (debugging, diffing) receive a generated markdown projection, not the source IR.
- Schema migrations must be handled explicitly when IR models evolve.
- Validation and QA logic can operate directly on structured fields rather than parsing free text.

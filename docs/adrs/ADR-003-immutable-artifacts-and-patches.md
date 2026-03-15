# ADR-003: Immutable Artifacts and Patches

**Status:** Accepted
**Date:** 2026-03-15

## Context
Pipeline stages run in sequence and downstream stages depend on upstream outputs. If an upstream artifact is silently mutated after the fact, downstream results become inconsistent. We also need a mechanism for human corrections that does not break reproducibility.

## Decision
Every stage output is an immutable, content-addressed artifact. Once written, an artifact is never modified in place. Human fixes are expressed as typed patch records that reference the original artifact by hash and describe the correction semantically. A patched artifact produces a new artifact with a new hash.

## Consequences
- Any pipeline run is fully reproducible given the same input artifacts and patches.
- Human corrections are auditable: each patch records who, when, what, and why.
- Storage grows append-only; garbage collection is a separate, explicit step.
- Downstream stages must declare which artifact hashes they consumed, enabling cache invalidation.

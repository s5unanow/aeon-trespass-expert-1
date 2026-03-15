# ADR-010: QA Is Release-Blocking

**Status:** Accepted
**Date:** 2026-03-15

## Context
The pipeline produces content that players rely on for gameplay. Errors in symbol recovery, block ordering, or translation can make rules ambiguous or wrong. We need a clear policy on when quality issues prevent publication rather than being logged and ignored.

## Decision
QA findings classified as `error` or `critical` severity block the publish step. No page with an unresolved error-or-above finding may be included in a release artifact. Lower-severity findings (warning, info) are recorded but do not block.

## Consequences
- The QA stage must run before publish and its output is a hard gate, not advisory.
- Each QA check declares its severity level; adding a new check does not require changing the gate logic.
- Human reviewers can override a finding by applying a typed patch (ADR-003) that resolves it.
- Release cadence depends on QA pass rate; investing in extraction accuracy directly unblocks releases.

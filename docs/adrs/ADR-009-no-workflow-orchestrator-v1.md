# ADR-009: No Workflow Orchestrator in V1

**Status:** Accepted
**Date:** 2026-03-15

## Context
Workflow orchestrators like Prefect, Dagster, and Temporal provide retry logic, observability, and distributed execution. However, adopting one in v1 adds significant dependency weight, learning curve, and infrastructure requirements when the pipeline is still single-machine and fewer than ten stages.

## Decision
V1 uses a custom in-process stage runner: a simple Python loop that executes stages sequentially, passing typed artifacts between them. Retry, logging, and error handling are implemented inline. An orchestrator may be adopted in a later version if scale or team size demands it.

## Consequences
- No external infrastructure (database, scheduler, UI) is needed to run the pipeline.
- The stage runner is easy to debug with standard Python tooling (pdb, logging, tracebacks).
- Parallelism and distributed execution are deferred; v1 processes one page at a time.
- Migration to an orchestrator later requires wrapping each stage as a task, which the typed contracts (ADR-001) make straightforward.

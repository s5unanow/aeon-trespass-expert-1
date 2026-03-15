# ADR-002: Markdown Is Not Source of Truth

**Status:** Accepted
**Date:** 2026-03-15

## Context
Early prototypes used markdown files as the working format between stages. This created ambiguity: edits to markdown could silently diverge from the structured data, and re-parsing markdown to recover structure proved fragile and lossy.

## Decision
Markdown may be generated for debugging, human review, or export, but it is never treated as a source of truth. No pipeline stage reads markdown as input. Any human correction must be applied through typed patch records against the IR (see ADR-003).

## Consequences
- Markdown output is disposable and can be regenerated at any time from the IR.
- Human reviewers see markdown for convenience but submit corrections via structured patch files.
- There is no markdown parser in the critical pipeline path, reducing a class of parsing bugs.
- Documentation or wiki exports are clearly labeled as derived artifacts.

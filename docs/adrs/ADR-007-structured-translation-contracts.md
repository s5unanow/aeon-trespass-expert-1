# ADR-007: Structured Translation Contracts

**Status:** Accepted
**Date:** 2026-03-15

## Context
Translation must preserve block structure, inline symbol tokens, and formatting metadata. Sending free-form text to an LLM and parsing the response is fragile: the model may merge blocks, drop symbols, or alter formatting. We need a contract that constrains both input and output.

## Decision
Translation uses block-level structured contracts: `TranslationBatchV1` (input) and `TranslationResultV1` (output). Each block carries its type, text content, inline symbol tokens, and ordering. The LLM receives and returns JSON conforming to these schemas, enabling mechanical validation of the round-trip.

## Consequences
- Every translated block can be validated for structural integrity (symbol count, block count, type preservation).
- Prompt engineering targets a well-defined JSON schema rather than free-form prose instructions.
- Batch boundaries are explicit, allowing retry at the block level rather than re-translating entire pages.
- Schema evolution follows the same versioning rules as other IR models (ADR-001).

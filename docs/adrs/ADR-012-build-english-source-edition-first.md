# ADR-012: Build English Source Edition First

**Status:** Accepted
**Date:** 2026-03-15

## Context
The source rulebooks are in English. Translation adds a large surface area of potential errors (prompt engineering, symbol preservation, grammatical correctness). Debugging extraction bugs and translation bugs simultaneously makes root-cause analysis difficult.

## Decision
Build and validate a complete English source edition before enabling translation to other languages. The English edition exercises the full pipeline -- ingest, extract, symbols, structure, render, QA -- without the translation stage. Translation is added only after extraction correctness is confirmed.

## Consequences
- Extraction and structuring bugs are isolated and fixed before translation introduces its own error class.
- The English edition serves as the ground-truth reference for translation QA comparisons.
- Users who only need English get a working product sooner.
- The translation stage can assume its input is already validated, simplifying its own error handling.

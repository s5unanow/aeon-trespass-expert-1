# ADR-005: Docling as Layout Evidence

**Status:** Accepted
**Date:** 2026-03-15

## Context
PyMuPDF provides low-level word and span data but does not understand document layout: columns, reading order, heading hierarchy, or table regions. A layout-analysis layer is needed to group words into logical blocks and establish reading order.

## Decision
Docling is used as the layout and reading-order evidence provider. Its output (block boundaries, reading order, region classification) is treated as evidence that the structuring stage consumes, not as canonical text. The canonical text always comes from PyMuPDF.

## Consequences
- Layout evidence and text extraction are decoupled; either can be upgraded independently.
- The structuring stage merges PyMuPDF text with Docling layout, resolving conflicts explicitly.
- Docling errors affect block ordering but cannot silently corrupt the extracted text.
- If Docling is replaced later, only the layout-evidence adapter changes; downstream IR contracts remain stable.

# ADR-006: Symbol Catalog and Template Matching

**Status:** Accepted
**Date:** 2026-03-15

## Context
Aeon Trespass rulebooks use inline icons (progress, sanity, damage, etc.) that PDFs encode as embedded images or custom glyphs, not as Unicode text. Regex-based extraction cannot recover these symbols because they have no textual representation in the PDF stream.

## Decision
Icons are recovered via a curated symbol catalog combined with OpenCV template matching. Each known icon is registered with a canonical name (e.g., `sym.progress`) and one or more reference templates at expected sizes. The symbol stage scans page images for template matches and inserts symbolic tokens into the IR at matched positions.

## Consequences
- New icons require adding a reference image and catalog entry, not writing new parsing code.
- Template matching tolerates minor rendering variations across PDF versions.
- False positives are possible; confidence thresholds and QA checks (ADR-010) mitigate this.
- The symbol catalog is versioned alongside the pipeline and can be extended per-book.

# Quality Improvement Plan

Based on the audit of all 83 pages (139 issues found).

## Issue Breakdown

| Category | Pages Affected | Issue Count | Severity |
|----------|---------------|-------------|----------|
| Long paragraphs (>1000 chars) | 60 | 95 | High |
| Decorative icons leaking | 25 | 25 | Medium |
| Duplicate text blocks | 4 | 9 | Medium |
| English text remaining | 4 | 6 | Medium |
| Glued text (missing breaks) | 4 | 4 | Medium |
| Pages with few blocks (≤2) | 6 | — | Low (mostly index/cover pages) |

---

## Fix 1: Long Paragraphs (95 issues, 60 pages)

**Root cause**: `real_block_builder.py` paragraph gap detection (1.5x font size) misses breaks in:
- Dense body text where line spacing is consistent (no vertical gaps)
- Card/callout text that's extracted as one text flow
- Index/reference pages (p0077-p0081) where entire page content is one block

**Fix approach — 3 tiers**:

### Tier A: Aggressive paragraph splitting in block builder
- **Where**: `real_block_builder.py`
- **What**: After gap detection, apply a secondary split: if a paragraph exceeds 600 chars, split at the last sentence boundary (`. ` followed by uppercase) before the limit
- **Impact**: Resolves ~70% of long paragraphs

### Tier B: Index/reference page handler
- **Where**: New function in `real_block_builder.py`
- **What**: Pages 77-81 are keyword indices. Detect by font/layout pattern (short bold term + definition). Split each term into its own block with `kind="definition"` or at minimum separate paragraphs
- **Impact**: Fixes the 5 worst pages (4000-5400 chars)

### Tier C: Card/callout detection
- **Where**: `real_block_builder.py`
- **What**: Detect bounded text regions (game cards, callout boxes) by identifying text clusters with distinct bounding box regions separated from main body. Create `CalloutBlock` for these
- **Impact**: Fixes glued text from game card content (p0012.b018, p0028)

---

## Fix 2: Decorative Icons (25 pages)

**Root cause**: Symbol matcher matches board tile markers, art textures, terrain icons, etc. that are decorative PDF elements, not inline content icons.

**Fix approach**:

### Option A: Filter in symbol catalog (recommended)
- **Where**: `configs/symbols/ato_core_v1_1.symbols.toml`
- **What**: Add `inline = false` flag to decorative symbol entries. Update `real_block_builder.py` to skip non-inline symbols when inserting icons into text blocks
- **Impact**: Eliminates all 25 pages' decorative icon issues at the source

### Option B: Filter in render export (already done partially)
- **Where**: `IconInline.tsx` HIDDEN_ICONS set
- **What**: Already hides them in the UI, but they still pollute the data
- **Status**: Done — but not a complete fix since data still carries them

---

## Fix 3: Duplicate Text (4 pages, 9 duplicates)

**Root cause**: The block builder creates duplicate blocks when:
- The same text appears in overlapping PDF text spans (common in headers/footers)
- Table cells are extracted as separate text spans that get grouped identically

**Fix approach**:

### Deduplication pass in block builder
- **Where**: `real_block_builder.py`, at the end of `build_page_ir_real()`
- **What**: After all blocks are built, compare consecutive blocks. If two blocks have identical text content (first 80 chars match), merge or drop the duplicate
- **Impact**: Fixes all 9 duplicate instances

---

## Fix 4: English Text Remaining (4 pages)

**Root cause**: Two sub-causes:
1. Game-specific terms not in concept registry (e.g., "Scouts", "Acclimation", "Delve", "Pharos")
2. OCR artifacts creating compound words ("WisdomBAN")

**Fix approach**:

### Expand concept registry
- **Where**: `configs/glossary/concepts.toml`
- **What**: Add missing game terms:
  - "Scouts" → "Разведчики"
  - "Acclimation" → "Акклиматизация"
  - "Delve" → "Погружение"
  - "Pharos" → "Фарос" (proper noun, transliterate)
  - "Inverted Combat Paradigm" → "Инвертированная Боевая Парадигма"
- **Impact**: Won't auto-fix (needs re-translation), but ensures consistency in future runs

### Fix OCR gluing
- **Where**: `pymupdf_extractor.py` or `real_block_builder.py`
- **What**: Detect spans that are suspiciously concatenated (e.g., camelCase-like patterns in non-English text: "WisdomBAN"). Insert space or split
- **Impact**: Fixes OCR compound word artifacts

---

## Fix 5: Glued Text (4 pages)

**Root cause**: Missing whitespace between adjacent text spans. When PyMuPDF extracts text, some spans end without trailing space and the next span starts without leading space.

**Fix approach**:

### Space insertion in block builder
- **Where**: `real_block_builder.py`, in the span-to-text conversion
- **What**: When concatenating adjacent text spans into a paragraph, check if span N ends without whitespace and span N+1 starts without whitespace. If so, insert a space
- **Impact**: Fixes all 4 glued text pages

---

## Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| 1 | Fix 1A — Sentence-boundary paragraph splitting | Small | Fixes ~70 long paragraphs |
| 2 | Fix 3 — Deduplication pass | Small | Fixes 9 duplicates |
| 3 | Fix 5 — Space insertion | Small | Fixes 4 glued text pages |
| 4 | Fix 2A — Catalog inline flag | Small | Cleans 25 pages of icon noise |
| 5 | Fix 1B — Index page handler | Medium | Fixes 5 worst pages |
| 6 | Fix 4 — Concept registry expansion | Small | Consistency for future runs |
| 7 | Fix 1C — Callout detection | Large | Proper card/box rendering |

**Recommended order**: 1A → 3 → 5 → 2A → 1B → 4 → 1C

Fixes 1A, 3, and 5 are all in `real_block_builder.py` and can be done together in one pass.

# ADR-013: Retire Tesseract from OCR Fallback Stack

**Status:** Accepted
**Date:** 2026-04-19
**Supersedes:** portions of ADR-005 (Docling as Layout Evidence) that contemplated a tertiary Tesseract hOCR/ALTO/PAGE layer

## Context

Early architecture (see PROJECT_ARCHITECTURE.md §§ "Extraction layers") contemplated a three-tier OCR evidence stack: PyMuPDF native text, Docling layout, PaddleOCR hard-page fallback, with Tesseract held in reserve as a tertiary emitter of hOCR/ALTO/PAGE structural evidence for pages that defeated the first two layers. In practice, no page in the source corpus has exercised that tertiary path: Docling plus PaddleOCR have absorbed every hard-page case encountered during Phase 1 and Phase 2 extraction work. Carrying Tesseract as a contingent dependency imposes ongoing costs — container size, toolchain pinning, configuration surface in `configs/extraction/*.toml`, CI image builds — without any corresponding extraction benefit. The retirement was executed in S5U-592 (PR #273, merge SHA `c6b06f2fbfeb4c6e678ae5e6d88eb240f9c83fff`), which removed residual Tesseract configuration keys and governance-doc references. This ADR records the architectural decision behind that code change.

## Decision

Tesseract is removed from the OCR fallback stack. PaddleOCR is the single OCR fallback layer. The pipeline ships with no tesseract dependency — no binary expected on PATH, no Python `pytesseract` wrapper, no configuration surface. If a future hard page defeats PaddleOCR, the response is to file a fresh ADR that evaluates alternatives (Surya, newer PaddleOCR models, a targeted human-patch workflow) rather than to reopen the retired Tesseract path.

## Consequences

- Extraction configuration surface shrinks: no Tesseract-specific TOML keys, no `pytesseract` import, no hOCR/ALTO/PAGE emitter stub.
- CI images are smaller and faster to build; there is no risk of Tesseract version drift between dev and CI environments.
- The OCR fallback contract is simplified to a single implementation (PaddleOCR), making the evidence-merge stage in `atr_pipeline/stages/extract_layout/` easier to reason about.
- Any future "need an additional OCR layer" discussion starts from a clean architecture decision record, not from rehabilitating a historically-dormant path. Documentation that still references a "Paddle/Tesseract fallback" or "tertiary Tesseract layer" is historical and must be updated or explicitly scoped.
- Governance docs reference this ADR (plus S5U-592) when citing the retirement rationale. The legacy citation of ADR-003 for this rationale (present in `docs/PROJECT_ARCHITECTURE.md:650` prior to S5U-638) was a dangling reference — ADR-003 is about immutable artifacts, not OCR — and has been corrected to point here.

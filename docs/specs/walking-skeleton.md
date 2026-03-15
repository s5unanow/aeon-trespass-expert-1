# Walking Skeleton Spec

**Status:** Accepted
**Date:** 2026-03-15

## Goal

Prove the end-to-end pipeline works by processing a single synthetic PDF page through every stage: **ingest -> extract -> symbols -> structure -> translate -> render -> QA**. The skeleton uses minimal, hand-crafted input so failures point to pipeline wiring, not content complexity.

## Synthetic Input

A one-page PDF containing:

- **Heading:** "Attack Test"
- **Paragraph:** "Gain 1 [sym.progress] Progress."

The `[sym.progress]` token is rendered as the progress icon image inline in the PDF. A matching template image is provided in the symbol catalog.

## Pipeline Stages and Expected Behavior

| Stage       | Input                        | Output                          |
|-------------|------------------------------|---------------------------------|
| **Ingest**      | Synthetic PDF file           | `IngestPageV1` artifact (raw page bytes, metadata) |
| **Extract**     | `IngestPageV1`               | `ExtractedPageV1` (words with bounding boxes, spans, font metadata) |
| **Symbols**     | `ExtractedPageV1` + page image + symbol catalog | `SymbolPageV1` (text with `sym.progress` token placed at matched position) |
| **Structure**   | `SymbolPageV1` + layout evidence | `StructuredPageV1` (heading block + paragraph block, reading order) |
| **Translate**   | `TranslationBatchV1` from `StructuredPageV1` | `TranslationResultV1` (target-language blocks preserving symbol tokens) |
| **Render**      | `StructuredPageV1` or translated result | `RenderPageV1` JSON payload consumable by the React reader |
| **QA**          | All upstream artifacts        | `QAReportV1` with zero error/critical findings |

## Done Criteria

1. **Full pass:** Running `atr run --input synthetic.pdf` executes all seven stages without error.
2. **Heading preserved:** The `StructuredPageV1` contains a block of type `heading` with text `"Attack Test"`.
3. **Symbol recovered:** The `SymbolPageV1` contains a `sym.progress` token with a bounding-box inside the paragraph region.
4. **Translation round-trip:** The `TranslationResultV1` has the same block count, same symbol count, and each symbol token is preserved verbatim.
5. **Render payload valid:** The `RenderPageV1` JSON validates against the generated JSON Schema.
6. **QA green:** The `QAReportV1` reports zero findings at `error` or `critical` severity.
7. **Artifacts immutable:** Every stage output is content-addressed; re-running with the same input produces the same hashes.

## Out of Scope

- Multi-page documents
- Real rulebook content (IP-sensitive material)
- OCR / scanned pages
- Concurrent or distributed execution
- Reader UI beyond payload validation

# ADR-004: PyMuPDF as Native PDF Extractor

**Status:** Accepted
**Date:** 2026-03-15

## Context
The pipeline must extract text, spans, images, and geometric information from PDF source books. We need a fast, well-maintained library that provides word-level bounding boxes, font metadata, and embedded image access without requiring an external service or OCR for born-digital PDFs.

## Decision
PyMuPDF (fitz) is the native PDF evidence layer. It supplies word positions, font/span attributes, embedded images, and page geometry. All raw extraction data flows through PyMuPDF before any higher-level layout analysis.

## Consequences
- Word-level bounding boxes and font metadata are available from the first pipeline stage.
- Embedded images and vector paths can be extracted without a separate tool.
- PyMuPDF is a C-extension dependency; builds must ensure the native library is present.
- OCR-dependent pages (scanned content) will require an additional path, but born-digital pages are handled natively.

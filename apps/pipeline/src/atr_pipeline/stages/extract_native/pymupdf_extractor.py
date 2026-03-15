"""PyMuPDF native text/image evidence extractor."""

from __future__ import annotations

from pathlib import Path

import fitz

from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import (
    ImageBlockEvidence,
    NativePageV1,
    SpanEvidence,
    WordEvidence,
)


def extract_native_page(
    pdf_path: Path,
    *,
    page_number: int,
    document_id: str,
) -> NativePageV1:
    """Extract native evidence from a single PDF page.

    Uses both word-level and dict-level extraction:
    - Words for simple text extraction with bboxes
    - Dict for accurate font name/size from spans

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-based page number.
        document_id: Document identifier.

    Returns:
        NativePageV1 with words, spans, and image blocks.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    page_rect = page.rect

    # --- Word extraction ---
    raw_words = page.get_text("words")
    words: list[WordEvidence] = []
    for i, w in enumerate(raw_words):
        words.append(
            WordEvidence(
                word_id=f"w{i:04d}",
                text=w[4],
                bbox=Rect(x0=w[0], y0=w[1], x1=w[2], y1=w[3]),
            )
        )

    # --- Span extraction (for font info) ---
    spans: list[SpanEvidence] = []
    page_dict = page.get_text("dict")
    span_idx = 0
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # text blocks only
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span.get("bbox", (0, 0, 0, 0))
                spans.append(
                    SpanEvidence(
                        span_id=f"s{span_idx:04d}",
                        text=span.get("text", ""),
                        bbox=Rect(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
                        font_name=span.get("font", ""),
                        font_size=span.get("size", 0.0),
                        flags=span.get("flags", 0),
                        color=span.get("color", 0),
                    )
                )
                span_idx += 1

    # --- Image block extraction ---
    image_blocks: list[ImageBlockEvidence] = []
    for i, img_info in enumerate(page.get_images(full=True)):
        xref = img_info[0]
        try:
            img_rects = page.get_image_rects(xref)
            if img_rects:
                r = img_rects[0]
                image_blocks.append(
                    ImageBlockEvidence(
                        image_id=f"img{i:04d}",
                        bbox=Rect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1),
                        width_px=img_info[2],
                        height_px=img_info[3],
                        xref=xref,
                    )
                )
        except Exception:
            pass  # Skip images that can't be located

    doc.close()

    page_id = f"p{page_number:04d}"
    return NativePageV1(
        document_id=document_id,
        page_id=page_id,
        page_number=page_number,
        dimensions_pt=PageDimensions(width=page_rect.width, height=page_rect.height),
        words=words,
        spans=spans,
        image_blocks=image_blocks,
        extractor_meta={"engine": "pymupdf"},
    )

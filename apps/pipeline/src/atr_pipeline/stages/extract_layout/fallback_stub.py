"""OCR/layout fallback stub — placeholder for PaddleOCR/Tesseract integration.

This module will be used for hard pages where native extraction
and Docling both fail to produce reliable results.
"""

from __future__ import annotations

from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1


def ocr_fallback_stub(native_page: NativePageV1) -> LayoutPageV1:
    """Return an empty layout result — no OCR fallback available yet."""
    return LayoutPageV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
    )

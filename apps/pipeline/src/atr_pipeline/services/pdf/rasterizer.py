"""Page rasterization — render PDF pages to PNG at configurable DPI."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import fitz


def render_page_png(pdf_path: Path, page_number: int, *, dpi: int = 300) -> bytes:
    """Render a single PDF page to PNG bytes.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-based page number.
        dpi: Resolution in dots per inch.

    Returns:
        PNG image bytes.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()
    return cast(bytes, png_bytes)

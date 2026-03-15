"""PDF fingerprinting — compute stable hash and page count."""

from __future__ import annotations

from pathlib import Path

import fitz

from atr_pipeline.utils.hashing import sha256_file


def fingerprint_pdf(pdf_path: Path) -> tuple[str, int]:
    """Return (sha256_hex, page_count) for a PDF file."""
    sha = sha256_file(pdf_path)
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return sha, count

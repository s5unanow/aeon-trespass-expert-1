"""PDF image extraction — extract embedded images via PyMuPDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

# Minimum dimensions (in pixels) for an image to be considered significant.
MIN_WIDTH_PX = 50
MIN_HEIGHT_PX = 50


@dataclass(frozen=True)
class ExtractedImage:
    """An image extracted from a PDF page."""

    page_number: int
    image_id: str
    xref: int
    width_px: int
    height_px: int
    image_bytes: bytes
    extension: str  # e.g. ".png", ".jpeg"


def extract_page_images(
    pdf_path: Path,
    *,
    page_number: int,
    min_width: int = MIN_WIDTH_PX,
    min_height: int = MIN_HEIGHT_PX,
) -> list[ExtractedImage]:
    """Extract significant embedded images from a single PDF page.

    Uses PyMuPDF's ``Document.extract_image(xref)`` to get the raw image
    bytes for each image object referenced on the page.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-based page number.
        min_width: Minimum image width in pixels to include.
        min_height: Minimum image height in pixels to include.

    Returns:
        List of extracted images that meet the size threshold.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    results: list[ExtractedImage] = []

    for idx, img_info in enumerate(page.get_images(full=True)):
        xref = img_info[0]
        try:
            img_data = doc.extract_image(xref)
        except Exception:
            continue

        if not img_data or not img_data.get("image"):
            continue

        width = img_data.get("width", 0)
        height = img_data.get("height", 0)

        if width < min_width or height < min_height:
            continue

        # Map PyMuPDF ext to file extension
        ext = img_data.get("ext", "png")
        extension = f".{ext}" if not ext.startswith(".") else ext

        results.append(
            ExtractedImage(
                page_number=page_number,
                image_id=f"p{page_number:04d}.img{idx:04d}",
                xref=xref,
                width_px=width,
                height_px=height,
                image_bytes=img_data["image"],
                extension=extension,
            )
        )

    doc.close()
    return results

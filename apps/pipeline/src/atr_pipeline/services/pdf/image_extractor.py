"""PDF image extraction — extract embedded images via PyMuPDF."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz

# Minimum dimensions (in pixels) for an image to be considered significant.
MIN_WIDTH_PX = 50
MIN_HEIGHT_PX = 50

# S5U-700: reject near-blank watermark/background crops whose decoded
# luminance is almost white and whose variance is low enough that no
# visible content is present. A pure-black or saturated-colour logo has
# a low mean (or high saturation) and will NOT be rejected — the gate is
# the conjunction of "bright" AND "low-variance".
_BLANK_MEAN_THRESHOLD = 240.0
_BLANK_VARIANCE_THRESHOLD = 50.0

_logger = logging.getLogger(__name__)


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


def _is_blank_crop(image_bytes: bytes) -> bool:
    """Return True if the decoded image is effectively a blank watermark.

    Loads the bytes via PIL, converts to grayscale, and rejects only when
    the image is both **bright** (mean ≥ 240) AND **low-variance** (< 50).
    Both halves of the conjunction are needed to avoid false positives on
    legitimate solid-colour logos or screenshots with dark subjects. The
    function returns ``False`` on decode failure (fail-open — existing
    dimension gate still applies, and the operator would rather ship a
    suspect crop than silently drop a real figure).
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover — PIL is a transitive dep
        return False
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            gray = img.convert("L")
            pixels = gray.tobytes()
            if not pixels:
                return False
            n = len(pixels)
            total = sum(pixels)
            mean = total / n
            # Compute variance via a single pass on the byte buffer.
            sq_total = sum(p * p for p in pixels)
            variance = sq_total / n - mean * mean
    except Exception as exc:
        _logger.debug("blank-crop gate decode failed: %s", exc)
        return False
    return mean >= _BLANK_MEAN_THRESHOLD and variance < _BLANK_VARIANCE_THRESHOLD


def extract_page_images(
    pdf_path: Path,
    *,
    page_number: int,
    min_width: int = MIN_WIDTH_PX,
    min_height: int = MIN_HEIGHT_PX,
    reject_blank: bool = True,
) -> list[ExtractedImage]:
    """Extract significant embedded images from a single PDF page.

    Uses PyMuPDF's ``Document.extract_image(xref)`` to get the raw image
    bytes for each image object referenced on the page.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-based page number.
        min_width: Minimum image width in pixels to include.
        min_height: Minimum image height in pixels to include.
        reject_blank: When True (S5U-700 default), drop crops that are
            effectively blank watermarks (mean ≥ 240, variance < 50).

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

        image_bytes: bytes = img_data["image"]
        if reject_blank and _is_blank_crop(image_bytes):
            _logger.info(
                "Rejecting blank/watermark crop: page %d xref %d (%dx%d, %d bytes)",
                page_number,
                xref,
                width,
                height,
                len(image_bytes),
            )
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
                image_bytes=image_bytes,
                extension=extension,
            )
        )

    doc.close()
    return results

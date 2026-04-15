"""PaddleOCR layout/text fallback adapter.

Runs PaddleOCR on a page raster when the native text layer is sparse
(hard pages flagged by the difficulty scorer) or when the primary
Docling extractor fails. Produces a ``LayoutPageV1`` with OCR-derived
text zones and word-level evidence in PDF-point coordinates.

PaddleOCR is an optional dependency — when the ``paddleocr`` package
is not installed, the adapter degrades to an empty result and the
stage keeps whatever the primary extractor produced.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atr_pipeline.stages.extract_layout.difficulty_scorer import compute_difficulty
from atr_schemas.common import Rect
from atr_schemas.layout_page_v1 import LayoutPageV1, LayoutZone
from atr_schemas.native_page_v1 import NativePageV1, WordEvidence

if TYPE_CHECKING:
    from paddleocr import PaddleOCR

log = logging.getLogger(__name__)

_ocr_instance: Any = None
_paddleocr_unavailable = False


def _get_ocr() -> PaddleOCR | None:
    """Lazy-load the PaddleOCR engine (heavy: loads detection + recognition models)."""
    global _ocr_instance, _paddleocr_unavailable
    if _ocr_instance is not None:
        return _ocr_instance
    if _paddleocr_unavailable:
        return None
    try:
        from paddleocr import PaddleOCR

        _ocr_instance = PaddleOCR(lang="en", show_log=False, use_angle_cls=False)
        log.info("PaddleOCR engine initialized")
        return _ocr_instance
    except ImportError:
        _paddleocr_unavailable = True
        log.warning("PaddleOCR not installed — pip install 'atr-pipeline[ocr]'")
        return None


def extract_layout_ocr(
    native_page: NativePageV1,
    page_image_path: Path | None = None,
    *,
    dpi: int = 300,
) -> LayoutPageV1:
    """Extract layout zones and text-line evidence via OCR on a page raster.

    PaddleOCR emits **line-level** polygons, so each detection becomes one
    ``LayoutZone`` and one ``ocr_words`` entry at line granularity — this
    differs from the true per-word evidence in ``NativePageV1.words``. The
    ``WordEvidence`` type is reused for coordinate/text typing only.

    All bounding boxes are scaled from image pixels to PDF points via
    ``72 / dpi``.

    Returns an empty ``LayoutPageV1`` (no zones, no words) when:
      * ``page_image_path`` is missing
      * PaddleOCR is not installed
      * PaddleOCR raises during inference
      * The engine returns no detections
    """
    empty = _empty_layout(native_page)
    if page_image_path is None:
        return empty

    ocr = _get_ocr()
    if ocr is None:
        return empty

    detections = _run_paddleocr(ocr, page_image_path, native_page.page_id)
    if not detections:
        return empty

    scale = 72.0 / dpi
    zones: list[LayoutZone] = []
    words: list[WordEvidence] = []
    reading_order: list[str] = []

    for idx, (text, polygon, confidence) in enumerate(detections):
        bbox = _polygon_to_rect(polygon, scale)
        if bbox is None:
            continue
        zone_id = f"ocr{idx + 1:03d}"
        zones.append(
            LayoutZone(
                zone_id=zone_id,
                kind="body",
                bbox=bbox,
                confidence=confidence,
            )
        )
        words.append(
            WordEvidence(
                word_id=f"ocr_w{idx + 1:04d}",
                text=text,
                bbox=bbox,
            )
        )
        reading_order.append(zone_id)

    if not zones:
        return empty

    difficulty = compute_difficulty(native_page, zones)
    log.info("PaddleOCR extracted %d zones for %s", len(zones), native_page.page_id)
    return LayoutPageV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
        zones=zones,
        reading_order_candidates=[reading_order],
        difficulty=difficulty,
        ocr_words=words,
    )


def _run_paddleocr(
    ocr: Any,
    image_path: Path,
    page_id: str,
) -> list[tuple[str, list[list[float]], float]]:
    """Call PaddleOCR and normalize its result into (text, polygon, confidence)."""
    try:
        raw = ocr.ocr(str(image_path), cls=False)
    except Exception:
        log.warning("PaddleOCR inference failed for %s", page_id, exc_info=True)
        return []

    if not raw:
        return []

    # PaddleOCR v2.x returns [page_results] where page_results is a list of
    # [polygon, (text, confidence)] entries. Some versions return page_results
    # directly without the outer list — handle both shapes.
    page_results = raw[0] if raw and isinstance(raw[0], list) else raw
    if not page_results:
        return []

    out: list[tuple[str, list[list[float]], float]] = []
    for entry in page_results:
        parsed = _parse_detection(entry)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_detection(
    entry: Any,
) -> tuple[str, list[list[float]], float] | None:
    """Pull (text, polygon, confidence) out of a single PaddleOCR detection."""
    if not entry or len(entry) < 2:
        return None
    polygon = entry[0]
    payload = entry[1]
    if not polygon or not payload or len(payload) < 2:
        return None
    text = str(payload[0])
    try:
        confidence = float(payload[1])
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return text, [[float(p[0]), float(p[1])] for p in polygon], confidence


def _polygon_to_rect(polygon: list[list[float]], scale: float) -> Rect | None:
    """Convert a 4-point polygon in pixels to an axis-aligned Rect in PDF points."""
    if not polygon:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x0, x1 = min(xs) * scale, max(xs) * scale
    y0, y1 = min(ys) * scale, max(ys) * scale
    if x1 <= x0 or y1 <= y0:
        return None
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _empty_layout(native_page: NativePageV1) -> LayoutPageV1:
    """Fallback when OCR cannot run — no zones, no words, no difficulty."""
    return LayoutPageV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
    )

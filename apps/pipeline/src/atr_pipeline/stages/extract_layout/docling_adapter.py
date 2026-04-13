"""Docling layout evidence adapter.

Uses Docling's document understanding API to detect layout zones,
reading order, and region types from page raster images.
Falls back to a single body zone when Docling is not installed
or no page image is available.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atr_pipeline.stages.extract_layout.difficulty_scorer import compute_difficulty
from atr_schemas.common import Rect
from atr_schemas.layout_page_v1 import LayoutPageV1, LayoutZone
from atr_schemas.native_page_v1 import NativePageV1

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

log = logging.getLogger(__name__)

# Docling DocItemLabel.value -> LayoutZone kind
_LABEL_TO_KIND: dict[str, str] = {
    "caption": "caption",
    "checkbox_selected": "body",
    "checkbox_unselected": "body",
    "code": "body",
    "document_index": "body",
    "figure": "figure",
    "footnote": "footer",
    "formula": "body",
    "list_item": "body",
    "page_footer": "footer",
    "page_header": "header",
    "picture": "figure",
    "reference": "body",
    "section_header": "header",
    "table": "table",
    "text": "body",
    "title": "header",
}

_converter_instance: Any = None  # lazy singleton; typed as Any to avoid import


def _get_converter() -> DocumentConverter | None:
    """Lazy-load the Docling DocumentConverter (heavy: loads ML models)."""
    global _converter_instance
    if _converter_instance is not None:
        return _converter_instance
    try:
        from docling.document_converter import DocumentConverter

        _converter_instance = DocumentConverter()
        log.info("Docling converter initialized")
        return _converter_instance
    except ImportError:
        log.warning("Docling not installed — pip install 'atr-pipeline[layout]'")
        return None


def extract_layout_docling(
    native_page: NativePageV1,
    page_image_path: Path | None = None,
    *,
    dpi: int = 300,
) -> LayoutPageV1:
    """Extract layout zones using Docling, with stub fallback.

    When Docling is installed and a page raster is available, produces
    accurate zones with kind, bbox, and confidence from Docling's
    document understanding model. Falls back to a single body zone
    when Docling is unavailable or the image cannot be processed.
    """
    if page_image_path is not None:
        converter = _get_converter()
        if converter is not None:
            zones, reading_order = _run_docling(converter, page_image_path, native_page, dpi)
            if zones:
                difficulty = compute_difficulty(native_page, zones)
                return LayoutPageV1(
                    document_id=native_page.document_id,
                    page_id=native_page.page_id,
                    zones=zones,
                    reading_order_candidates=reading_order,
                    difficulty=difficulty,
                )

    return _stub_layout(native_page)


def _run_docling(
    converter: DocumentConverter,
    image_path: Path,
    native_page: NativePageV1,
    dpi: int,
) -> tuple[list[LayoutZone], list[list[str]]]:
    """Run Docling on a page raster and convert output to LayoutZones."""
    try:
        result = converter.convert(str(image_path))
    except Exception:
        log.warning("Docling conversion failed for %s", native_page.page_id, exc_info=True)
        return [], []

    doc = result.document
    scale = 72.0 / dpi  # pixel coords -> PDF points
    zones: list[LayoutZone] = []
    reading_order: list[str] = []

    for idx, (item, _level) in enumerate(doc.iterate_items()):
        if not item.prov:
            continue
        prov = item.prov[0]
        bbox = prov.bbox

        zone_id = f"z{idx + 1:03d}"
        label_str = item.label.value if hasattr(item.label, "value") else str(item.label)
        kind = _LABEL_TO_KIND.get(label_str, "body")

        zone = LayoutZone(
            zone_id=zone_id,
            kind=kind,
            bbox=Rect(
                x0=bbox.l * scale,
                y0=bbox.t * scale,
                x1=bbox.r * scale,
                y1=bbox.b * scale,
            ),
            confidence=float(getattr(prov, "confidence", 0.9)),
        )
        zones.append(zone)
        reading_order.append(zone_id)

    log.info("Docling extracted %d zones for %s", len(zones), native_page.page_id)
    return zones, [reading_order] if reading_order else []


def _stub_layout(native_page: NativePageV1) -> LayoutPageV1:
    """Single body zone fallback when Docling is unavailable."""
    dims = native_page.dimensions_pt
    body_zone = LayoutZone(
        zone_id="z001",
        kind="body",
        bbox=Rect(x0=50, y0=50, x1=dims.width - 50, y1=dims.height - 50),
        confidence=1.0,
    )
    zones = [body_zone]
    difficulty = compute_difficulty(native_page, zones)
    return LayoutPageV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
        zones=zones,
        difficulty=difficulty,
    )

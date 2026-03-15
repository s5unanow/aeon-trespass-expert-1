"""Docling layout evidence adapter — placeholder for real integration.

In production, this will call Docling's document understanding API
to produce zones, reading order candidates, and table/figure detections.
Currently returns a minimal stub result.
"""

from __future__ import annotations

from pathlib import Path

from atr_schemas.common import Rect
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1, LayoutZone
from atr_schemas.native_page_v1 import NativePageV1


def extract_layout_stub(
    native_page: NativePageV1,
    page_image_path: Path,
) -> LayoutPageV1:
    """Return a minimal layout result for simple single-column pages.

    This stub assumes the entire page is one body zone.
    Replace with real Docling integration for multi-column/complex pages.
    """
    dims = native_page.dimensions_pt
    body_zone = LayoutZone(
        zone_id="z001",
        kind="body",
        bbox=Rect(x0=50, y0=50, x1=dims.width - 50, y1=dims.height - 50),
        confidence=1.0,
    )

    difficulty = DifficultyScoreV1(
        page_id=native_page.page_id,
        column_count=1,
        native_text_coverage=1.0,
        extractor_agreement=1.0,
        hard_page=False,
        recommended_route="R1",
    )

    return LayoutPageV1(
        document_id=native_page.document_id,
        page_id=native_page.page_id,
        zones=[body_zone],
        difficulty=difficulty,
    )

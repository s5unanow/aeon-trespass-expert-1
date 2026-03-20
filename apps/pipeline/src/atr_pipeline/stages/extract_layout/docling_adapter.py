"""Docling layout evidence adapter — placeholder for real integration.

In production, this will call Docling's document understanding API
to produce zones, reading order candidates, and table/figure detections.
Currently returns a minimal stub result with real difficulty scoring.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.stages.extract_layout.difficulty_scorer import compute_difficulty
from atr_schemas.common import Rect
from atr_schemas.layout_page_v1 import LayoutPageV1, LayoutZone
from atr_schemas.native_page_v1 import NativePageV1


def extract_layout_stub(
    native_page: NativePageV1,
    page_image_path: Path | None = None,
) -> LayoutPageV1:
    """Return a minimal layout result with real difficulty scoring.

    Zone detection is still a stub (single body zone), but difficulty
    is computed from native evidence so hard pages are flagged.
    """
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

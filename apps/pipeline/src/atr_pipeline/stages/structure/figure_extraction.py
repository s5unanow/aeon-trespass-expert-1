"""Figure-candidate image filtering.

Extracted from ``real_block_builder`` in S5U-710. No behavior changes.

Provides the helpers the main structure orchestrator uses to decide
which PDF image blocks should be promoted to ``FigureBlock``:

* ``_significant_image_blocks`` — drop sub-threshold and footer-zone
  images so they never become figures,
* ``_image_overlaps_text`` — reject figure candidates that sit on top
  of text (decorative flourishes behind running prose).
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_schemas.native_page_v1 import ImageBlockEvidence, NativePageV1, SpanEvidence


def _significant_image_blocks(
    native: NativePageV1,
    cfg: StructureConfig,
) -> list[ImageBlockEvidence]:
    """Return image blocks large enough to warrant a FigureBlock.

    Filters by bounding-box size in PDF points and excludes images that sit
    entirely within the footer region.
    """
    results: list[ImageBlockEvidence] = []
    for img in native.image_blocks:
        w = img.bbox.x1 - img.bbox.x0
        h = img.bbox.y1 - img.bbox.y0
        if w < cfg.figure_min_width_pt or h < cfg.figure_min_height_pt:
            continue
        if img.bbox.y0 >= cfg.footer_y_threshold:
            continue
        results.append(img)
    return results


def _image_overlaps_text(
    img: ImageBlockEvidence,
    spans: list[SpanEvidence],
    tolerance: float = 5.0,
) -> bool:
    """Check whether an image's bbox substantially overlaps with text spans."""
    for span in spans:
        # If the bounding boxes overlap vertically and horizontally
        if (
            img.bbox.x0 < span.bbox.x1 + tolerance
            and img.bbox.x1 > span.bbox.x0 - tolerance
            and img.bbox.y0 < span.bbox.y1 + tolerance
            and img.bbox.y1 > span.bbox.y0 - tolerance
        ):
            return True
    return False

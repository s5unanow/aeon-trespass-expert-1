"""Regression tests for non-finite page-dimension handling (S5U-697 round-3).

Split out of ``test_annotation_mapping.py`` to keep that file under the
400-line ceiling enforced by ``scripts/check_file_length.py``.
"""

from __future__ import annotations

import math

from atr_pipeline.stages.render.annotation_builder import (
    AnnotationQualityConfig,
    build_facsimile_annotations,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline


def _para(bid: str, bbox: Rect, text: str) -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid,
        type="paragraph",
        bbox=bbox,
        children=[TextInline(text=text)],
    )


def test_non_finite_page_dimensions_return_empty() -> None:
    """NaN/Inf in PageDimensions must short-circuit to [] (S5U-697 round-3)."""
    nan, inf = math.nan, math.inf
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    for w, h in [(nan, 792.0), (612.0, nan), (inf, 792.0), (612.0, inf), (-inf, 792.0)]:
        en = PageIRV1(
            document_id="test",
            page_id="p0007",
            page_number=7,
            language=LanguageCode.EN,
            dimensions_pt=PageDimensions(width=w, height=h),
            blocks=[_para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=30), "Text")],
        )
        assert build_facsimile_annotations(en, quality=cfg) == [], (
            f"Non-finite page dims w={w}, h={h} must produce empty annotations"
        )

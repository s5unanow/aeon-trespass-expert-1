"""Regression tests for non-finite page-dimension handling.

Pins the *net effect* of the defense-in-depth stack that handles NaN/Inf
``PageDimensions``: empty annotations out, full stop. The stack has three
layers and the test below cannot fail any single layer in isolation (any
one of them alone catches the input); see the test docstring for the
S5U-722 retrospective.

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


def test_non_finite_page_dimensions_produce_empty_annotations() -> None:
    """NaN/Inf ``PageDimensions`` produce ``[]`` — defense-in-depth net effect.

    This test pins the *stack's* invariant, not any single guard. Three
    layers each independently produce ``[]`` for the inputs below:

    * ``annotation_builder.py:118-124`` — NaN-dim short-circuit (S5U-697
      round-3) returns ``[]`` before any per-block work.
    * ``annotation_builder.py:155-157`` — raw-coord ``math.isfinite``
      check drops every block before normalization (NaN/inf divisors
      would otherwise propagate).
    * ``annotation_safeguards.py:54-64`` — ``is_bbox_valid`` rejects
      zero-area NormRects, which is what the
      ``max(0, min(1, c/dim))`` clamp ladder produces from any
      NaN/inf divisor (NaN -> 1.0, inf -> 1.0, -inf -> 0.0; collapsed
      to width=0 or height=0).

    Reverting any *one* layer while leaving the other two in place
    keeps the test green — verified during S5U-703 review (W1) and
    captured in S5U-722. A narrower red-before per layer would require
    mocking the other two (Option B in S5U-722, deferred).
    """
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

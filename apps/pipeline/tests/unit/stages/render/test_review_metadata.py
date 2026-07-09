"""Focused review metadata coverage kept strict-mypy clean."""

from atr_pipeline.stages.render.annotation_builder import build_facsimile_annotations
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.common import ConfidenceMetrics, PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, TextInline


def _review_page() -> PageIRV1:
    block = HeadingBlock(
        block_id="p0007.b001",
        bbox=Rect(x0=10, y0=20, x1=200, y1=80),
        children=[TextInline(text="Components")],
    )
    return PageIRV1(
        document_id="review_doc",
        page_id="p0007",
        page_number=7,
        language=LanguageCode.EN,
        dimensions_pt=PageDimensions(width=612, height=792),
        blocks=[block],
        reading_order=[block.block_id],
        confidence=ConfidenceMetrics(native_text_coverage=0.91, page_confidence=0.87),
    )


def test_review_annotation_carries_block_ref() -> None:
    annotations = build_facsimile_annotations(_review_page())

    assert len(annotations) == 1
    assert annotations[0].block_ref == "p0007.b001"


def test_review_page_carries_source_confidence() -> None:
    rendered = build_render_page(_review_page())

    assert rendered.page.source_confidence == 0.87

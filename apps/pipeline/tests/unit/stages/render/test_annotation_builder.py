"""Tests for facsimile annotation builder."""

from __future__ import annotations

from atr_pipeline.stages.render.annotation_builder import build_facsimile_annotations
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    CaptionBlock,
    DividerBlock,
    HeadingBlock,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)


def _make_ir(
    *,
    lang: LanguageCode = LanguageCode.EN,
    dims: PageDimensions | None = None,
    blocks: list | None = None,
) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0007",
        page_number=7,
        language=lang,
        dimensions_pt=dims or PageDimensions(width=612.0, height=792.0),
        blocks=blocks or [],
    )


def _en_ir_with_blocks() -> PageIRV1:
    return _make_ir(
        lang=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Components")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=50, y0=100, x1=562, y1=200),
                children=[TextInline(text="This page shows game components.")],
            ),
            CaptionBlock(
                block_id="p0007.b003",
                bbox=Rect(x0=100, y0=600, x1=400, y1=630),
                children=[TextInline(text="Figure 1: Token layout")],
            ),
        ],
    )


def _ru_ir_with_blocks() -> PageIRV1:
    return _make_ir(
        lang=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Компоненты")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=50, y0=100, x1=562, y1=200),
                children=[TextInline(text="Игровые компоненты.")],
            ),
            CaptionBlock(
                block_id="p0007.b003",
                bbox=Rect(x0=100, y0=600, x1=400, y1=630),
                children=[TextInline(text="Рисунок 1: жетоны")],
            ),
        ],
    )


def test_basic_annotation_generation() -> None:
    """Builds annotations from EN IR blocks with bboxes."""
    en_ir = _en_ir_with_blocks()
    annotations = build_facsimile_annotations(en_ir)

    assert len(annotations) == 3
    # Sorted by priority descending: heading (100), paragraph (40), caption (60)
    assert annotations[0].kind == "title"
    assert annotations[0].text == "Components"
    assert annotations[0].priority == 100
    assert annotations[1].kind == "caption"
    assert annotations[1].priority == 60
    assert annotations[2].kind == "body"
    assert annotations[2].priority == 40


def test_annotations_with_ru_translation() -> None:
    """Paired EN/RU IRs produce annotations with translated_text."""
    en_ir = _en_ir_with_blocks()
    ru_ir = _ru_ir_with_blocks()
    annotations = build_facsimile_annotations(en_ir, ru_ir)

    assert len(annotations) == 3
    heading = annotations[0]
    assert heading.text == "Components"
    assert heading.translated_text == "Компоненты"

    caption = annotations[1]
    assert caption.text == "Figure 1: Token layout"
    assert caption.translated_text == "Рисунок 1: жетоны"


def test_bbox_normalization() -> None:
    """Bounding boxes are normalized to [0,1] using page dimensions."""
    en_ir = _make_ir(
        dims=PageDimensions(width=612.0, height=792.0),
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=Rect(x0=0, y0=0, x1=612, y1=792),
                children=[TextInline(text="Full page")],
            ),
        ],
    )
    annotations = build_facsimile_annotations(en_ir)

    assert len(annotations) == 1
    bbox = annotations[0].bbox
    assert bbox.x0 == 0.0
    assert bbox.y0 == 0.0
    assert abs(bbox.x1 - 1.0) < 1e-9
    assert abs(bbox.y1 - 1.0) < 1e-9


def test_bbox_clamped_to_unit_range() -> None:
    """Bboxes outside page bounds are clamped to [0,1]."""
    en_ir = _make_ir(
        dims=PageDimensions(width=100.0, height=100.0),
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=-10, y0=-5, x1=150, y1=120),
                children=[TextInline(text="Overflow text")],
            ),
        ],
    )
    annotations = build_facsimile_annotations(en_ir)

    bbox = annotations[0].bbox
    assert bbox.x0 == 0.0
    assert bbox.y0 == 0.0
    assert bbox.x1 == 1.0
    assert bbox.y1 == 1.0


def test_missing_dimensions_returns_empty() -> None:
    """No annotations when page dimensions are missing."""
    en_ir = _make_ir(
        dims=None,
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=Rect(x0=0, y0=0, x1=100, y1=50),
                children=[TextInline(text="Title")],
            ),
        ],
    )
    # Override dimensions_pt to None
    en_ir.dimensions_pt = None
    annotations = build_facsimile_annotations(en_ir)
    assert annotations == []


def test_blocks_without_bbox_skipped() -> None:
    """Blocks missing bbox are skipped."""
    en_ir = _make_ir(
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=None,
                children=[TextInline(text="No bbox heading")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=10, x1=200, y1=50),
                children=[TextInline(text="Has bbox")],
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert len(annotations) == 1
    assert annotations[0].text == "Has bbox"


def test_divider_and_unknown_blocks_skipped() -> None:
    """Divider and unknown blocks produce no annotations."""
    en_ir = _make_ir(
        blocks=[
            DividerBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=0, y0=400, x1=612, y1=402),
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert annotations == []


def test_empty_text_blocks_skipped() -> None:
    """Blocks with no text content produce no annotations."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=200, y1=50),
                children=[],
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert annotations == []


def test_unmatched_ru_block_gives_empty_translation() -> None:
    """RU IR with no matching block_id gives empty translated_text."""
    en_ir = _make_ir(
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Title")],
            ),
        ]
    )
    ru_ir = _make_ir(
        lang=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0007.b099",  # different block_id
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Заголовок")],
            ),
        ],
    )
    annotations = build_facsimile_annotations(en_ir, ru_ir)
    assert len(annotations) == 1
    assert annotations[0].text == "Title"
    assert annotations[0].translated_text == ""

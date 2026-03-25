"""Tests for facsimile annotation builder."""

from __future__ import annotations

from atr_pipeline.stages.render.annotation_builder import (
    AnnotationQualityConfig,
    build_facsimile_annotations,
)
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
                bbox=Rect(x0=50, y0=100, x1=200, y1=130),
                children=[TextInline(text="This page shows game components.")],
            ),
            CaptionBlock(
                block_id="p0007.b003",
                bbox=Rect(x0=100, y0=600, x1=250, y1=620),
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
                bbox=Rect(x0=50, y0=100, x1=200, y1=130),
                children=[TextInline(text="Игровые компоненты.")],
            ),
            CaptionBlock(
                block_id="p0007.b003",
                bbox=Rect(x0=100, y0=600, x1=250, y1=620),
                children=[TextInline(text="Рисунок 1: жетоны")],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Basic annotation generation
# ---------------------------------------------------------------------------


def test_basic_annotation_generation() -> None:
    """Builds annotations from EN IR blocks with bboxes."""
    en_ir = _en_ir_with_blocks()
    annotations = build_facsimile_annotations(en_ir)

    assert len(annotations) == 3
    assert annotations[0].kind == "title"
    assert annotations[0].text == "Components"
    assert annotations[0].priority == 100


def test_annotations_with_ru_translation() -> None:
    """Paired EN/RU IRs produce annotations with translated_text."""
    en_ir = _en_ir_with_blocks()
    ru_ir = _ru_ir_with_blocks()
    annotations = build_facsimile_annotations(en_ir, ru_ir)

    assert len(annotations) == 3
    heading = annotations[0]
    assert heading.text == "Components"
    assert heading.translated_text == "Компоненты"


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
    # Full-page bbox exceeds max_bbox_area — use permissive config
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    annotations = build_facsimile_annotations(en_ir, quality=cfg)

    assert len(annotations) == 1
    bbox = annotations[0].bbox
    assert bbox.x0 == 0.0
    assert bbox.y0 == 0.0
    assert abs(bbox.x1 - 1.0) < 1e-9
    assert abs(bbox.y1 - 1.0) < 1e-9


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


def test_divider_blocks_skipped() -> None:
    """Divider blocks produce no annotations."""
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
                block_id="p0007.b099",
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


# ---------------------------------------------------------------------------
# Per-annotation quality filtering
# ---------------------------------------------------------------------------


def test_identical_en_ru_text_dropped() -> None:
    """Annotations where EN == RU (codes, numbers) are filtered out."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=100, y1=30),
                children=[TextInline(text="AM0308")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=40, x1=100, y1=60),
                children=[TextInline(text="Real content here")],
            ),
        ]
    )
    ru_ir = _make_ir(
        lang=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=100, y1=30),
                children=[TextInline(text="AM0308")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=40, x1=100, y1=60),
                children=[TextInline(text="Реальный контент")],
            ),
        ],
    )
    annotations = build_facsimile_annotations(en_ir, ru_ir)
    assert len(annotations) == 1
    assert annotations[0].text == "Real content here"


def test_oversized_bbox_dropped() -> None:
    """Annotations covering more than max_bbox_area are filtered out."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=0, y0=0, x1=612, y1=500),  # huge bbox
                children=[TextInline(text="Giant block")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=10, x1=80, y1=30),  # small bbox
                children=[TextInline(text="Small block")],
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert len(annotations) == 1
    assert annotations[0].text == "Small block"


def test_garbled_ocr_text_dropped() -> None:
    """Annotations with garbled OCR text are filtered out."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=100, y1=30),
                children=[TextInline(text="_____+_____=_____")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=40, x1=100, y1=60),
                children=[TextInline(text="Normal readable text")],
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert len(annotations) == 1
    assert annotations[0].text == "Normal readable text"


def test_valid_short_labels_preserved() -> None:
    """Short but valid game labels (single chars, numbers) are kept."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=30, y1=25),
                children=[TextInline(text="I")],  # single-char label
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=40, x1=50, y1=55),
                children=[TextInline(text="HP")],  # two-char abbreviation
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert len(annotations) == 2


def test_identical_case_insensitive_dropped() -> None:
    """Case-insensitive identity is detected."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=100, y1=30),
                children=[TextInline(text="TITAN")],
            ),
        ]
    )
    ru_ir = _make_ir(
        lang=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=100, y1=30),
                children=[TextInline(text="Titan")],
            ),
        ],
    )
    annotations = build_facsimile_annotations(en_ir, ru_ir)
    assert len(annotations) == 0


# ---------------------------------------------------------------------------
# Page-level overlay suppression
# ---------------------------------------------------------------------------


def test_page_suppressed_when_too_many_annotations() -> None:
    """Page with excessive annotations is suppressed entirely."""
    blocks = [
        ParagraphBlock(
            block_id=f"p0007.b{i:03d}",
            bbox=Rect(x0=10 + i, y0=10 + i * 5, x1=50 + i, y1=20 + i * 5),
            children=[TextInline(text=f"Block number {i}")],
        )
        for i in range(50)
    ]
    en_ir = _make_ir(blocks=blocks)
    cfg = AnnotationQualityConfig(max_annotation_count=30)
    annotations = build_facsimile_annotations(en_ir, quality=cfg)
    assert annotations == []


def test_page_suppressed_when_total_area_too_large() -> None:
    """Page where total annotation area exceeds threshold is suppressed."""
    blocks = [
        ParagraphBlock(
            block_id=f"p0007.b{i:03d}",
            bbox=Rect(x0=0, y0=i * 100, x1=612, y1=i * 100 + 80),
            children=[TextInline(text=f"Wide block {i}")],
        )
        for i in range(5)
    ]
    en_ir = _make_ir(blocks=blocks)
    # Each bbox is full-width ~10% height = 0.1 area, total ~0.5
    cfg = AnnotationQualityConfig(
        max_bbox_area=0.15,
        max_total_area=0.3,
    )
    annotations = build_facsimile_annotations(en_ir, quality=cfg)
    assert annotations == []


def test_page_with_good_quality_not_suppressed() -> None:
    """Clean page with few good annotations passes quality checks."""
    en_ir = _en_ir_with_blocks()
    ru_ir = _ru_ir_with_blocks()
    annotations = build_facsimile_annotations(en_ir, ru_ir)
    assert len(annotations) == 3


def test_custom_quality_config() -> None:
    """Quality config thresholds are respected."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=0, y0=0, x1=400, y1=400),  # area ~0.27
                children=[TextInline(text="Medium block")],
            ),
        ]
    )
    # Default max_bbox_area=0.10 would filter this out
    strict = AnnotationQualityConfig(max_bbox_area=0.10)
    assert build_facsimile_annotations(en_ir, quality=strict) == []

    # Permissive config keeps it
    permissive = AnnotationQualityConfig(max_bbox_area=0.50, max_total_area=1.0)
    assert len(build_facsimile_annotations(en_ir, quality=permissive)) == 1


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
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    annotations = build_facsimile_annotations(en_ir, quality=cfg)

    assert len(annotations) == 1
    bbox = annotations[0].bbox
    assert bbox.x0 == 0.0
    assert bbox.y0 == 0.0
    assert bbox.x1 == 1.0
    assert bbox.y1 == 1.0


def test_page_suppressed_when_drop_ratio_too_high() -> None:
    """Page is suppressed when most candidates are dropped by quality filters."""
    # 6 blocks: 4 with identical EN/RU (dropped), 2 with real translations
    en_blocks = [
        ParagraphBlock(
            block_id=f"p0007.b{i:03d}",
            bbox=Rect(x0=10, y0=10 + i * 30, x1=100, y1=30 + i * 30),
            children=[TextInline(text=f"CODE{i}")],
        )
        for i in range(4)
    ] + [
        ParagraphBlock(
            block_id="p0007.b010",
            bbox=Rect(x0=10, y0=200, x1=100, y1=220),
            children=[TextInline(text="Real text here")],
        ),
        ParagraphBlock(
            block_id="p0007.b011",
            bbox=Rect(x0=10, y0=230, x1=100, y1=250),
            children=[TextInline(text="Another real block")],
        ),
    ]
    ru_blocks = [
        ParagraphBlock(
            block_id=f"p0007.b{i:03d}",
            bbox=Rect(x0=10, y0=10 + i * 30, x1=100, y1=30 + i * 30),
            children=[TextInline(text=f"CODE{i}")],  # identical → dropped
        )
        for i in range(4)
    ] + [
        ParagraphBlock(
            block_id="p0007.b010",
            bbox=Rect(x0=10, y0=200, x1=100, y1=220),
            children=[TextInline(text="Реальный текст")],
        ),
        ParagraphBlock(
            block_id="p0007.b011",
            bbox=Rect(x0=10, y0=230, x1=100, y1=250),
            children=[TextInline(text="Ещё один блок")],
        ),
    ]
    en_ir = _make_ir(blocks=en_blocks)
    ru_ir = _make_ir(lang=LanguageCode.RU, blocks=ru_blocks)
    # 4/6 = 66.7% dropped — exceeds max_drop_ratio=0.5
    cfg = AnnotationQualityConfig(max_drop_ratio=0.5)
    assert build_facsimile_annotations(en_ir, ru_ir, quality=cfg) == []


def test_page_not_suppressed_when_drop_ratio_acceptable() -> None:
    """Page with low drop ratio is not suppressed."""
    # 4 blocks: 1 with identical EN/RU (dropped), 3 with real translations
    en_blocks = [
        ParagraphBlock(
            block_id="p0007.b001",
            bbox=Rect(x0=10, y0=10, x1=100, y1=30),
            children=[TextInline(text="CODE1")],
        ),
        ParagraphBlock(
            block_id="p0007.b002",
            bbox=Rect(x0=10, y0=40, x1=100, y1=60),
            children=[TextInline(text="Real text one")],
        ),
        ParagraphBlock(
            block_id="p0007.b003",
            bbox=Rect(x0=10, y0=70, x1=100, y1=90),
            children=[TextInline(text="Real text two")],
        ),
        ParagraphBlock(
            block_id="p0007.b004",
            bbox=Rect(x0=10, y0=100, x1=100, y1=120),
            children=[TextInline(text="Real text three")],
        ),
    ]
    ru_blocks = [
        ParagraphBlock(
            block_id="p0007.b001",
            bbox=Rect(x0=10, y0=10, x1=100, y1=30),
            children=[TextInline(text="CODE1")],  # identical → dropped
        ),
        ParagraphBlock(
            block_id="p0007.b002",
            bbox=Rect(x0=10, y0=40, x1=100, y1=60),
            children=[TextInline(text="Текст один")],
        ),
        ParagraphBlock(
            block_id="p0007.b003",
            bbox=Rect(x0=10, y0=70, x1=100, y1=90),
            children=[TextInline(text="Текст два")],
        ),
        ParagraphBlock(
            block_id="p0007.b004",
            bbox=Rect(x0=10, y0=100, x1=100, y1=120),
            children=[TextInline(text="Текст три")],
        ),
    ]
    en_ir = _make_ir(blocks=en_blocks)
    ru_ir = _make_ir(lang=LanguageCode.RU, blocks=ru_blocks)
    # 1/4 = 25% dropped — below max_drop_ratio=0.5
    cfg = AnnotationQualityConfig(max_drop_ratio=0.5)
    result = build_facsimile_annotations(en_ir, ru_ir, quality=cfg)
    assert len(result) == 3


def test_numeric_game_values_not_garbled() -> None:
    """Multi-digit game values like '10', '+2' are not flagged as garbled."""
    en_ir = _make_ir(
        blocks=[
            ParagraphBlock(
                block_id="p0007.b001",
                bbox=Rect(x0=10, y0=10, x1=30, y1=25),
                children=[TextInline(text="10")],
            ),
            ParagraphBlock(
                block_id="p0007.b002",
                bbox=Rect(x0=10, y0=40, x1=50, y1=55),
                children=[TextInline(text="1-3")],
            ),
        ]
    )
    annotations = build_facsimile_annotations(en_ir)
    assert len(annotations) == 2

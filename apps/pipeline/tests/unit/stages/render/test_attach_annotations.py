"""Tests for _attach_annotations override logic in RenderStage."""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

from atr_pipeline.config.models import PageOverride, RenderConfig
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.render.stage import RenderStage
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, ParagraphBlock, TextInline
from atr_schemas.render_page_v1 import RenderFacsimile, RenderPageV1


def _make_ir(
    *,
    lang: LanguageCode = LanguageCode.EN,
    blocks: list | None = None,
) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0006",
        page_number=6,
        language=lang,
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        blocks=blocks or [],
    )


def _en_ir() -> PageIRV1:
    return _make_ir(
        lang=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="p0006.b001",
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Components")],
            ),
            ParagraphBlock(
                block_id="p0006.b002",
                bbox=Rect(x0=50, y0=100, x1=200, y1=130),
                children=[TextInline(text="AI Cards")],
            ),
            ParagraphBlock(
                block_id="p0006.b003",
                bbox=Rect(x0=50, y0=140, x1=200, y1=170),
                children=[TextInline(text="Divider Cards")],
            ),
        ],
    )


def _ru_ir() -> PageIRV1:
    return _make_ir(
        lang=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0006.b001",
                level=1,
                bbox=Rect(x0=50, y0=40, x1=300, y1=80),
                children=[TextInline(text="Компоненты")],
            ),
            ParagraphBlock(
                block_id="p0006.b002",
                bbox=Rect(x0=50, y0=100, x1=200, y1=130),
                children=[TextInline(text="Карты ИИ")],
            ),
            ParagraphBlock(
                block_id="p0006.b003",
                bbox=Rect(x0=50, y0=140, x1=200, y1=170),
                children=[TextInline(text="Разделительные карты")],
            ),
        ],
    )


def _make_render_page() -> RenderPageV1:
    """Build a minimal RenderPageV1 with facsimile set."""
    from atr_schemas.render_page_v1 import RenderPageMeta

    return RenderPageV1(
        page=RenderPageMeta(
            id="p0006",
            title="Components",
        ),
        facsimile=RenderFacsimile(
            raster_src="rasters/p0006__150dpi.png",
            width_px=1224,
            height_px=1584,
        ),
    )


def _mock_ctx() -> StageContext:
    ctx = create_autospec(StageContext, instance=True)
    ctx.document_id = "test_doc"
    ctx.logger = MagicMock()
    return ctx


def _load_ir_side_effect(en_ir: PageIRV1 | None, ru_ir: PageIRV1 | None) -> object:
    """Return a side_effect callable for _load_page_ir_by_lang."""

    def _load(ctx: StageContext, page_id: str, lang: str) -> PageIRV1 | None:
        if lang == "en":
            return en_ir
        if lang == "ru":
            return ru_ir
        return None

    return _load


# ---------------------------------------------------------------------------
# facsimile_annotations = false
# ---------------------------------------------------------------------------


def test_annotations_disabled_by_override() -> None:
    """facsimile_annotations=false suppresses all annotations for a page."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()
    override = PageOverride(facsimile_annotations=False)

    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, override)

    assert render_page.facsimile is not None
    assert render_page.facsimile.annotations == []
    ctx.logger.info.assert_any_call("Facsimile %s: annotations disabled by override", "p0006")


def test_annotations_enabled_when_override_is_none() -> None:
    """When override is None, annotations are built normally."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()

    stage._load_page_ir_by_lang = _load_ir_side_effect(_en_ir(), _ru_ir())  # type: ignore[assignment]
    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, None)

    assert render_page.facsimile is not None
    assert len(render_page.facsimile.annotations) == 3


def test_annotations_enabled_when_flag_is_true() -> None:
    """facsimile_annotations=true does not suppress annotations."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()
    override = PageOverride(facsimile_annotations=True)

    stage._load_page_ir_by_lang = _load_ir_side_effect(_en_ir(), _ru_ir())  # type: ignore[assignment]
    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, override)

    assert render_page.facsimile is not None
    assert len(render_page.facsimile.annotations) == 3


# ---------------------------------------------------------------------------
# facsimile_annotation_keep_texts
# ---------------------------------------------------------------------------


def test_keep_texts_filters_annotations() -> None:
    """facsimile_annotation_keep_texts filters to only matching EN texts."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()
    override = PageOverride(
        facsimile_annotation_keep_texts=["AI Cards"],
    )

    stage._load_page_ir_by_lang = _load_ir_side_effect(_en_ir(), _ru_ir())  # type: ignore[assignment]
    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, override)

    assert render_page.facsimile is not None
    assert len(render_page.facsimile.annotations) == 1
    assert render_page.facsimile.annotations[0].text == "AI Cards"


def test_keep_texts_multiple_matches() -> None:
    """Multiple keep_texts entries match multiple annotations."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()
    override = PageOverride(
        facsimile_annotation_keep_texts=["AI Cards", "Divider Cards"],
    )

    stage._load_page_ir_by_lang = _load_ir_side_effect(_en_ir(), _ru_ir())  # type: ignore[assignment]
    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, override)

    assert render_page.facsimile is not None
    assert len(render_page.facsimile.annotations) == 2
    texts = {a.text for a in render_page.facsimile.annotations}
    assert texts == {"AI Cards", "Divider Cards"}


def test_keep_texts_none_keeps_all_annotations() -> None:
    """Override without keep_texts keeps all annotations."""
    stage = RenderStage()
    ctx = _mock_ctx()
    render_page = _make_render_page()
    render_cfg = RenderConfig()
    override = PageOverride()  # no keep_texts set

    stage._load_page_ir_by_lang = _load_ir_side_effect(_en_ir(), _ru_ir())  # type: ignore[assignment]
    stage._attach_annotations(ctx, render_page, "p0006", render_cfg, override)

    assert render_page.facsimile is not None
    assert len(render_page.facsimile.annotations) == 3

"""Caption-to-figure folding tests for page_builder (S5U-700).

Red-before confirmation: at main @ bdb4b1b, ``page_builder`` did not
recognize ``CaptionBlock`` — it only handled paragraph/heading/table/
list_item/figure. A CaptionBlock emitted by the structure semantic
resolver fell through the elif chain and was dropped from the render
output entirely (or, once the attached ``type="caption"`` branch in
S5U-700 landed, became a floating paragraph). These tests fail at the
pre-fix commit because the ``figures[asset_id].caption`` field was
always empty.
"""

from __future__ import annotations

from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.common import Rect
from atr_schemas.page_ir_v1 import (
    CaptionBlock,
    FigureBlock,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _ir_with_caption() -> PageIRV1:
    fig = FigureBlock(
        block_id="p0042.fig.p0042.img0000",
        bbox=_rect(50, 100, 400, 300),
        asset_id="p0042.img0000",
    )
    caption = CaptionBlock(
        block_id="p0042.b009",
        bbox=_rect(50, 310, 400, 325),
        figure_block_id=fig.block_id,
        children=[TextInline(text="Zone 2 example")],
    )
    body = ParagraphBlock(
        block_id="p0042.b002",
        bbox=_rect(50, 400, 400, 440),
        children=[TextInline(text="Body prose")],
    )
    return PageIRV1(
        document_id="ato_core_v1_1",
        page_id="p0042",
        page_number=42,
        language="en",
        blocks=[body, fig, caption],
    )


class TestCaptionFolding:
    def test_caption_folds_into_figure(self) -> None:
        """CaptionBlock text lands on RenderFigure.caption, not as a paragraph."""
        render = build_render_page(_ir_with_caption())
        assert "p0042.img0000" in render.figures
        assert render.figures["p0042.img0000"].caption == "Zone 2 example"
        block_ids = [b.id for b in render.blocks]
        # Caption block removed from the linear stream because it was consumed.
        assert "p0042.b009" not in block_ids
        # The figure and body are still present.
        assert "p0042.fig.p0042.img0000" in block_ids
        assert "p0042.b002" in block_ids

    def test_caption_without_figure_kept_as_paragraph(self) -> None:
        """Orphan CaptionBlock (figure_block_id matches nothing) survives as prose."""
        orphan = CaptionBlock(
            block_id="p0042.b009",
            bbox=_rect(50, 310, 400, 325),
            figure_block_id="does.not.exist",
            children=[TextInline(text="Floating caption")],
        )
        ir = PageIRV1(
            document_id="ato_core_v1_1",
            page_id="p0042",
            page_number=42,
            language="en",
            blocks=[orphan],
        )
        render = build_render_page(ir)
        # Caption block survived as a paragraph — text not lost.
        assert any(b.id == "p0042.b009" and b.kind == "paragraph" for b in render.blocks)

    def test_figure_without_caption_has_empty_caption_field(self) -> None:
        """Regression: figures without a CaptionBlock still emit with caption=""."""
        fig = FigureBlock(
            block_id="p0042.fig.p0042.img0000",
            bbox=_rect(50, 100, 400, 300),
            asset_id="p0042.img0000",
        )
        ir = PageIRV1(
            document_id="ato_core_v1_1",
            page_id="p0042",
            page_number=42,
            language="en",
            blocks=[fig],
        )
        render = build_render_page(ir)
        assert render.figures["p0042.img0000"].caption == ""

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

    def test_orphan_caption_emits_render_caption_block(self) -> None:
        """S5U-737: a CaptionBlock whose ``figure_block_id`` does not point
        at any FigureBlock on the page is now emitted as a
        ``RenderCaptionBlock`` so the translatable prose survives to the
        reader. Pre-S5U-737 the silent ``continue`` in page_builder
        dropped the block entirely.

        Red-before confirmation: at commit 906a1a7 (main HEAD before this
        PR) the page_builder loop matched ``isinstance(block, CaptionBlock)``
        and ``continue``d unconditionally; the assertion below failed
        because ``render.blocks`` was empty.
        """
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
        captions = [b for b in render.blocks if b.kind == "caption"]
        assert len(captions) == 1, (
            f"orphan CaptionBlock must emit exactly one RenderCaptionBlock; "
            f"got {[b.kind for b in render.blocks]}"
        )
        assert captions[0].id == "p0042.b009"
        # Translatable prose is preserved verbatim.
        text_children = [c.text for c in captions[0].children if c.kind == "text"]
        assert text_children == ["Floating caption"]

    def test_caption_with_empty_figure_block_id_emits_render_caption_block(self) -> None:
        """S5U-737: a CaptionBlock whose ``figure_block_id`` is the empty
        default (``""``) is also orphan per the schema. Both shapes
        (dangling pointer and unset default) must reach the same
        RenderCaptionBlock branch.

        Adversarial input: rather than a dangling pointer the block
        simply has the default unset value — the rendering must apply
        in both shapes.
        """
        orphan = CaptionBlock(
            block_id="p0042.b009",
            bbox=_rect(50, 310, 400, 325),
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
        captions = [b for b in render.blocks if b.kind == "caption"]
        assert len(captions) == 1
        assert captions[0].id == "p0042.b009"

    def test_attached_caption_does_not_emit_render_caption_block(self) -> None:
        """S5U-737 regression sentinel: an *attached* CaptionBlock (one
        whose ``figure_block_id`` resolves to a FigureBlock on the page)
        must continue to fold into ``RenderFigure.caption`` and NOT
        appear as a top-level RenderCaptionBlock — otherwise we'd
        duplicate every figure caption.
        """
        render = build_render_page(_ir_with_caption())
        # No top-level caption blocks — attached caption was consumed.
        assert all(b.kind != "caption" for b in render.blocks), (
            f"attached caption leaked into top-level blocks: {[b.kind for b in render.blocks]}"
        )
        # Caption text is on the figure record.
        assert render.figures["p0042.img0000"].caption == "Zone 2 example"

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

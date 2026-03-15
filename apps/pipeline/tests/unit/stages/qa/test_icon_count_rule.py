"""Tests for the icon count QA rule."""

from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderIconInline,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderTextInline,
)


def _make_ir(lang: LanguageCode, icon_count: int) -> PageIRV1:
    children = [TextInline(text="Text ")]
    for i in range(icon_count):
        children.append(IconInline(symbol_id="sym.progress", instance_id=f"inst.{i}"))
    children.append(TextInline(text=" end."))
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=lang,
        blocks=[
            HeadingBlock(block_id="p0001.b001", children=[TextInline(text="H")]),
            ParagraphBlock(block_id="p0001.b002", children=children),  # type: ignore[arg-type]
        ],
        reading_order=["p0001.b001", "p0001.b002"],
    )


def _make_render(icon_count: int) -> RenderPageV1:
    children = [RenderTextInline(text="Text ")]
    for _ in range(icon_count):
        children.append(RenderIconInline(symbol_id="sym.progress", alt="P"))
    children.append(RenderTextInline(text=" end."))
    return RenderPageV1(
        page=RenderPageMeta(id="p0001"),
        blocks=[
            RenderHeadingBlock(id="p0001.b001", children=[RenderTextInline(text="H")]),
            RenderParagraphBlock(id="p0001.b002", children=children),  # type: ignore[arg-type]
        ],
    )


def test_passing_case() -> None:
    """All icon counts match — no QA issues."""
    source = _make_ir(LanguageCode.EN, 1)
    target = _make_ir(LanguageCode.RU, 1)
    render = _make_render(1)

    records = evaluate_icon_count(source, target, render)
    assert records == []


def test_target_missing_icon() -> None:
    """Target IR lost an icon — should produce error."""
    source = _make_ir(LanguageCode.EN, 1)
    target = _make_ir(LanguageCode.RU, 0)
    render = _make_render(0)

    records = evaluate_icon_count(source, target, render)
    assert len(records) >= 1
    assert any(r.code == "ICON_COUNT_SRC_TGT_MISMATCH" for r in records)
    assert all(r.severity.value == "error" for r in records)


def test_render_missing_icon() -> None:
    """Render page lost an icon — should produce error."""
    source = _make_ir(LanguageCode.EN, 1)
    target = _make_ir(LanguageCode.RU, 1)
    render = _make_render(0)

    records = evaluate_icon_count(source, target, render)
    assert len(records) >= 1
    assert any(r.code == "ICON_COUNT_TGT_RENDER_MISMATCH" for r in records)

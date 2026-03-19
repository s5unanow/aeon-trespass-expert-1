"""Tests for dead PDF page reference QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.dead_page_ref_rule import evaluate_dead_page_refs
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _page(blocks: list[RenderParagraphBlock]) -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title="Test", source_page_number=1),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _para(block_id: str, text: str) -> RenderParagraphBlock:
    return RenderParagraphBlock(
        id=block_id,
        children=[RenderTextInline(text=text)],
    )


# Build Russian "стр. 16" from Unicode escapes to avoid RUF001
_STR_DOT_16 = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + ". 16"
_STR_NO_DOT = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + " 35"
_STR_NO_SPACE = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + ".16"
# "см. стр. 16"
_SM_STR = "".join(chr(c) for c in [0x441, 0x43C]) + ". " + _STR_DOT_16


def test_detects_russian_page_ref_with_dot() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1
    assert records[0].code == "DEAD_PAGE_REF"


def test_detects_russian_page_ref_without_dot() -> None:
    page = _page([_para("b1", _STR_NO_DOT)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_russian_page_ref_no_space() -> None:
    page = _page([_para("b1", _STR_NO_SPACE)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_embedded_russian_ref() -> None:
    page = _page([_para("b1", _SM_STR)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_english_p_dot() -> None:
    page = _page([_para("b1", "see p. 42 for details")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_english_page() -> None:
    page = _page([_para("b1", "refer to page 10")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_english_page_case_insensitive() -> None:
    page = _page([_para("b1", "see Page 5")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_passes_clean_text() -> None:
    clean = "".join(chr(c) for c in [0x41F, 0x440, 0x438, 0x432, 0x435, 0x442]) + " 123"
    page = _page([_para("b1", clean)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 0


def test_one_record_per_block() -> None:
    """Multiple refs in one block produce only one record."""
    text = _STR_DOT_16 + " and " + _STR_NO_DOT
    block = RenderParagraphBlock(
        id="b1",
        children=[
            RenderTextInline(text=text),
        ],
    )
    page = _page([block])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_severity_is_warning() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].severity.value == "warning"


def test_layer_is_render() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].layer.value == "render"


def test_entity_ref_is_block_id() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].entity_ref == "b1"

"""Tests for paragraph length QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.paragraph_length_rule import evaluate_paragraph_length
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


def test_flags_long_paragraph() -> None:
    """Block exceeding 1000 chars is flagged."""
    page = _page([_para("b1", "x" * 1001)])
    records = evaluate_paragraph_length(page)

    assert len(records) == 1
    assert records[0].code == "PARAGRAPH_TOO_LONG"
    assert records[0].entity_ref == "b1"


def test_passes_short_paragraph() -> None:
    """Block at exactly 1000 chars passes."""
    page = _page([_para("b1", "x" * 1000)])
    records = evaluate_paragraph_length(page)

    assert len(records) == 0


def test_custom_threshold() -> None:
    """Configurable max_chars threshold works."""
    page = _page([_para("b1", "x" * 501)])
    records = evaluate_paragraph_length(page, max_chars=500)

    assert len(records) == 1
    assert "501 chars" in records[0].message


def test_custom_threshold_passes() -> None:
    """Block under custom threshold passes."""
    page = _page([_para("b1", "x" * 500)])
    records = evaluate_paragraph_length(page, max_chars=500)

    assert len(records) == 0


def test_multiple_children_summed() -> None:
    """Text length is summed across all children in a block."""
    block = RenderParagraphBlock(
        id="b1",
        children=[
            RenderTextInline(text="x" * 600),
            RenderTextInline(text="y" * 500),
        ],
    )
    page = _page([block])
    records = evaluate_paragraph_length(page)

    assert len(records) == 1
    assert "1100 chars" in records[0].message


def test_multiple_blocks_flagged_independently() -> None:
    """Each long block gets its own record."""
    page = _page([_para("b1", "x" * 1500), _para("b2", "y" * 1200)])
    records = evaluate_paragraph_length(page)

    assert len(records) == 2
    refs = {r.entity_ref for r in records}
    assert refs == {"b1", "b2"}


def test_severity_is_warning() -> None:
    page = _page([_para("b1", "x" * 1001)])
    records = evaluate_paragraph_length(page)

    assert records[0].severity.value == "warning"


def test_layer_is_structure() -> None:
    page = _page([_para("b1", "x" * 1001)])
    records = evaluate_paragraph_length(page)

    assert records[0].layer.value == "structure"


def test_expected_actual_metadata() -> None:
    """Record contains expected/actual for diagnostics."""
    page = _page([_para("b1", "x" * 1234)])
    records = evaluate_paragraph_length(page)

    assert records[0].expected == {"max_chars": 1000}
    assert records[0].actual == {"chars": 1234}

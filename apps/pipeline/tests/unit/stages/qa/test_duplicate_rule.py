"""Tests for duplicate content detection QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.duplicate_rule import evaluate_duplicate_content
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


def test_flags_identical_consecutive_blocks() -> None:
    page = _page([_para("b1", "same text here"), _para("b2", "same text here")])
    records = evaluate_duplicate_content(page)

    assert len(records) == 1
    assert records[0].code == "DUPLICATE_CONTENT"
    assert records[0].entity_ref == "b2"


def test_flags_near_duplicate() -> None:
    """Blocks sharing >90% Jaccard similarity are flagged."""
    # 11 unique words shared, 1 differs -> Jaccard = 10/12 = 0.833
    page = _page(
        [
            _para("b1", "the quick brown fox jumps high over the lazy dog here now"),
            _para("b2", "the quick brown fox jumps high over the lazy cat here now"),
        ]
    )
    records = evaluate_duplicate_content(page, threshold=0.8)

    assert len(records) == 1


def test_passes_different_blocks() -> None:
    page = _page(
        [
            _para("b1", "completely different text here"),
            _para("b2", "nothing in common with previous block"),
        ]
    )
    records = evaluate_duplicate_content(page)

    assert len(records) == 0


def test_passes_single_block() -> None:
    page = _page([_para("b1", "only one block")])
    records = evaluate_duplicate_content(page)

    assert len(records) == 0


def test_passes_empty_page() -> None:
    page = _page([])
    records = evaluate_duplicate_content(page)

    assert len(records) == 0


def test_only_checks_consecutive_pairs() -> None:
    """Non-consecutive duplicates are not flagged."""
    page = _page(
        [
            _para("b1", "repeated text here now"),
            _para("b2", "something completely different here"),
            _para("b3", "repeated text here now"),
        ]
    )
    records = evaluate_duplicate_content(page)

    assert len(records) == 0


def test_custom_threshold() -> None:
    """Lower threshold catches less similar blocks."""
    page = _page(
        [
            _para("b1", "hello world foo bar baz"),
            _para("b2", "hello world foo qux quux"),
        ]
    )
    # Default threshold (0.9) should pass
    assert len(evaluate_duplicate_content(page)) == 0
    # Lower threshold should catch it
    assert len(evaluate_duplicate_content(page, threshold=0.3)) == 1


def test_chain_of_three_duplicates() -> None:
    """Three identical blocks produce two records (b2 and b3)."""
    page = _page(
        [
            _para("b1", "same text"),
            _para("b2", "same text"),
            _para("b3", "same text"),
        ]
    )
    records = evaluate_duplicate_content(page)

    assert len(records) == 2
    refs = [r.entity_ref for r in records]
    assert refs == ["b2", "b3"]


def test_severity_is_warning() -> None:
    page = _page([_para("b1", "dup text"), _para("b2", "dup text")])
    records = evaluate_duplicate_content(page)

    assert records[0].severity.value == "warning"


def test_layer_is_structure() -> None:
    page = _page([_para("b1", "dup text"), _para("b2", "dup text")])
    records = evaluate_duplicate_content(page)

    assert records[0].layer.value == "structure"


def test_message_references_preceding_block() -> None:
    page = _page([_para("b1", "dup text"), _para("b2", "dup text")])
    records = evaluate_duplicate_content(page)

    assert "b1" in records[0].message

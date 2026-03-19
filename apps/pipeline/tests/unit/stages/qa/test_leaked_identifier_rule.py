"""Tests for leaked technical identifier QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.leaked_identifier_rule import evaluate_leaked_identifiers
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _page(blocks: list[RenderParagraphBlock], title: str = "Заголовок") -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title=title, source_page_number=1),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _para(block_id: str, text: str) -> RenderParagraphBlock:
    return RenderParagraphBlock(
        id=block_id,
        children=[RenderTextInline(text=text)],
    )


def test_detects_document_id_pattern() -> None:
    """Pattern like ato_core_v1_1 is flagged."""
    page = _page([_para("b1", "Коллекция ato_core_v1_1 содержит")])
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 1
    assert records[0].code == "LEAKED_TECHNICAL_ID"
    assert "ato_core_v1_1" in records[0].message


def test_detects_unknown_placeholder() -> None:
    """Standalone UNKNOWN is flagged."""
    page = _page([_para("b1", "Автор: UNKNOWN")])
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 1
    assert "UNKNOWN" in records[0].message


def test_detects_snake_case_in_cyrillic() -> None:
    """Snake-case token with ≥3 segments in Cyrillic context is flagged."""
    page = _page([_para("b1", "Получите бонус foo_bar_baz_qux.")])
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 1
    assert "foo_bar_baz_qux" in records[0].message


def test_ignores_clean_text() -> None:
    """Normal Cyrillic text produces no records."""
    page = _page([_para("b1", "Получите 1 Прогресс.")])
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 0


def test_ignores_snake_case_in_latin_only() -> None:
    """Snake-case tokens in pure Latin text are not flagged (could be legit)."""
    page = _page([_para("b1", "Use foo_bar_baz for config.")])
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 0


def test_flags_title_with_doc_id() -> None:
    """Page title containing a doc-ID pattern is flagged."""
    page = _page([], title="ato_core_v1_1")
    records = evaluate_leaked_identifiers(page)

    assert len(records) == 1
    assert records[0].entity_ref == "page.title"


def test_one_record_per_block() -> None:
    """Multiple matches within a single block produce only one record."""
    page = _page(
        [
            _para("b1", "UNKNOWN ato_core_v1_1"),
        ]
    )
    records = evaluate_leaked_identifiers(page)

    # Only one record for the block (first match wins, then break)
    block_records = [r for r in records if r.entity_ref == "b1"]
    assert len(block_records) == 1

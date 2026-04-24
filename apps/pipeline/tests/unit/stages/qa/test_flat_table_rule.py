"""Tests for the flat_table QA rule (S5U-704).

The rule flags ``RenderTableBlock`` entries that carry a long run of flat
inline children with no ``RenderTableRowBlock`` grandchildren — the
signature of a chart whose row/cell structure was stripped during
structure recovery.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.flat_table_rule import evaluate_flat_table
from atr_schemas.enums import QALayer, Severity
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTableBlock,
    RenderTableCellBlock,
    RenderTableRowBlock,
    RenderTextInline,
)


def _page(blocks: list) -> RenderPageV1:
    return RenderPageV1(
        schema_version="render_page.v1",
        document_version="en",
        presentation_mode="article",
        page=RenderPageMeta(id="p0054", title=""),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0054"),
    )


def _flat_table(id_: str, n: int) -> RenderTableBlock:
    return RenderTableBlock(
        id=id_,
        children=[RenderTextInline(text=f"cell {i}") for i in range(n)],
    )


def _structured_table(id_: str, n_rows: int, n_cols: int) -> RenderTableBlock:
    rows = [
        RenderTableRowBlock(
            id=f"{id_}.r{r}",
            cells=[
                RenderTableCellBlock(
                    id=f"{id_}.r{r}.c{c}",
                    children=[RenderTextInline(text=f"r{r}c{c}")],
                )
                for c in range(n_cols)
            ],
        )
        for r in range(n_rows)
    ]
    return RenderTableBlock(id=id_, children=list(rows))


def test_large_flat_table_emits_error() -> None:
    """p0054 regression — a TableBlock with 177 flat inline children and
    no rows is flagged with code ``FLAT_TABLE_NO_ROWS`` at ERROR severity.
    """
    page = _page([_flat_table("p0054.b002", 177)])
    records = evaluate_flat_table(page)
    assert len(records) == 1
    rec = records[0]
    assert rec.code == "FLAT_TABLE_NO_ROWS"
    assert rec.severity == Severity.ERROR
    assert rec.layer == QALayer.STRUCTURE
    assert rec.entity_ref == "p0054.b002"
    assert "177" in rec.message


def test_small_flat_table_is_silent() -> None:
    """Happy path — a TableBlock with fewer than the threshold (20) flat
    inline children is too small to be a mis-flattened chart body; the
    rule must remain silent to avoid noise on legitimate split-header
    tables (which typically carry ≤6 inlines)."""
    page = _page([_flat_table("p0054.b001", 3)])
    assert evaluate_flat_table(page) == []


def test_structured_table_is_silent_at_any_size() -> None:
    """A table with RenderTableRowBlock children is structured — the rule
    must not fire regardless of how many inlines the rows contain."""
    page = _page([_structured_table("p0054.b002", n_rows=50, n_cols=3)])
    assert evaluate_flat_table(page) == []


def test_paragraph_blocks_are_ignored() -> None:
    """Adversarial — a ParagraphBlock with 25 inline children is not a
    table and must not be flagged."""
    para = RenderParagraphBlock(
        id="p0001.b001",
        children=[RenderTextInline(text=f"word {i}") for i in range(25)],
    )
    page = _page([para])
    assert evaluate_flat_table(page) == []


def test_threshold_edge_case_19_inlines_silent() -> None:
    """Edge — exactly 19 flat inlines (one below threshold) remains silent."""
    page = _page([_flat_table("p0054.b001", 19)])
    assert evaluate_flat_table(page) == []


def test_threshold_edge_case_20_inlines_fires() -> None:
    """Edge — exactly 20 flat inlines (the threshold) fires."""
    page = _page([_flat_table("p0054.b001", 20)])
    records = evaluate_flat_table(page)
    assert len(records) == 1
    assert records[0].code == "FLAT_TABLE_NO_ROWS"


def test_mixed_structured_and_flat_tables_on_same_page() -> None:
    """Two tables on a page — the flat one fires, the structured one is
    silent. The rule emits one record per flat table."""
    page = _page(
        [
            _structured_table("p0054.b001", n_rows=3, n_cols=3),
            _flat_table("p0054.b002", 50),
        ],
    )
    records = evaluate_flat_table(page)
    assert len(records) == 1
    assert records[0].entity_ref == "p0054.b002"


def test_mixed_inlines_with_single_row_is_structured() -> None:
    """If a TableBlock mixes flat inlines (e.g. stray whitespace) with one
    TableRowBlock, the presence of the row makes it structured — the flat
    inlines alongside don't trigger the rule."""
    row = RenderTableRowBlock(
        id="p0054.b002.r0",
        cells=[
            RenderTableCellBlock(
                id="p0054.b002.r0.c0",
                children=[RenderTextInline(text="A")],
            ),
        ],
    )
    table = RenderTableBlock(
        id="p0054.b002",
        children=[
            *[RenderTextInline(text=f"stray {i}") for i in range(25)],
            row,
        ],
    )
    page = _page([table])
    assert evaluate_flat_table(page) == []

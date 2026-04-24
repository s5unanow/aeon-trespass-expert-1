"""S5U-704 — page_builder translates structured TableBlock rows/cells."""

from __future__ import annotations

from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderTableBlock,
    RenderTableCellBlock,
    RenderTableRowBlock,
    RenderTextInline,
)


def _make_ir_with_structured_table() -> PageIRV1:
    """Build a PageIRV1 whose only block is a structured TableBlock."""
    row = TableRowBlock(
        block_id="p0054.b002.r0",
        header=True,
        cells=[
            TableCellBlock(
                block_id="p0054.b002.r0.c0",
                header=True,
                children=[TextInline(text="Wounded card", lang=LanguageCode.EN)],
            ),
            TableCellBlock(
                block_id="p0054.b002.r0.c1",
                header=True,
                children=[TextInline(text="BP deck", lang=LanguageCode.EN)],
            ),
            TableCellBlock(
                block_id="p0054.b002.r0.c2",
                header=True,
                children=[TextInline(text="AI deck", lang=LanguageCode.EN)],
            ),
        ],
    )
    return PageIRV1(
        document_id="doc",
        page_id="p0054",
        page_number=54,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(block_id="p0054.b002", children=[row]),
        ],
    )


def test_render_preserves_row_cell_nesting() -> None:
    ir = _make_ir_with_structured_table()
    render = build_render_page(ir)

    tables = [b for b in render.blocks if isinstance(b, RenderTableBlock)]
    assert len(tables) == 1
    assert tables[0].id == "p0054.b002"

    rows = [c for c in tables[0].children if isinstance(c, RenderTableRowBlock)]
    assert len(rows) == 1
    row = rows[0]
    assert row.header is True
    assert len(row.cells) == 3
    assert all(isinstance(c, RenderTableCellBlock) for c in row.cells)
    assert row.cells[0].header is True
    assert row.cells[0].children == [RenderTextInline(text="Wounded card")]
    assert row.cells[1].children == [RenderTextInline(text="BP deck")]
    assert row.cells[2].children == [RenderTextInline(text="AI deck")]


def test_render_preserves_legacy_flat_table_children() -> None:
    """Back-compat: an IR TableBlock whose children are flat inlines (legacy
    shape or the ``semantic_resolver._resolve_tables`` promotion path) must
    pass through to a RenderTableBlock with flat inline children so cached
    artifacts keep rendering."""
    ir = PageIRV1(
        document_id="doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="BP I", lang=LanguageCode.EN),
                    TextInline(text="AI deck", lang=LanguageCode.EN),
                ],
            )
        ],
    )
    render = build_render_page(ir)
    tables = [b for b in render.blocks if isinstance(b, RenderTableBlock)]
    assert len(tables) == 1
    assert all(isinstance(c, RenderTextInline) for c in tables[0].children)
    assert [c.text for c in tables[0].children if isinstance(c, RenderTextInline)] == [
        "BP I",
        "AI deck",
    ]

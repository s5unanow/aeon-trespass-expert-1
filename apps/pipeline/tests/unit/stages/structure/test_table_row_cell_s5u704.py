"""S5U-704 — structured table rows/cells in real_block_builder.

Covers the two emit paths that now produce ``TableRowBlock``/``TableCellBlock``
nesting instead of flat ``TextInline`` runs:

1. ``flush_table`` — the table-region accumulator. When a table region is
   configured and spans fall inside it, each visual row becomes a
   ``TableRowBlock`` whose ``cells`` are split by horizontal x-gap.
2. The heading-cell-group refusal path (S5U-698) — a heading line that
   splits into ≥2 cell groups emits a single ``TableRowBlock`` header row
   inside a standalone ``TableBlock``.

Both paths preserve the legacy text content while adding structure so the
reader can emit ``<table><tr><td>`` instead of a pre-wrap text wall.
"""

from __future__ import annotations

from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence
from atr_schemas.page_ir_v1 import (
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    iter_table_inlines,
)

_DIMS = PageDimensions(width=612, height=842)


def _span(
    span_id: str,
    text: str,
    *,
    y0: float,
    x0: float,
    x1: float,
    font: str = "Adonis-Regular",
    size: float = 9.0,
) -> SpanEvidence:
    return SpanEvidence(
        span_id=span_id,
        text=text,
        font_name=font,
        font_size=size,
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y0 + 12.0),
    )


def _three_column_body_spans() -> list[SpanEvidence]:
    """Three visual rows of 3 columns each, separated by large x-gaps.

    Matches the ATO p0054 chart: a label column (e.g. "BP I"), a BP-deck
    action column, an AI-deck action column. Horizontal gaps between
    columns are >25 pt so the default ``table_body_cell_split_gap_pt``
    threshold splits them into cells.
    """
    spans: list[SpanEvidence] = []
    counter = 0
    for ri, y in enumerate((200.0, 220.0, 240.0)):
        cols = [
            (f"BP {ri + 1}", 60.0, 90.0),
            ("Shuffle a BP card", 150.0, 260.0),
            ("Search the AI deck", 320.0, 460.0),
        ]
        for text, x0, x1 in cols:
            counter += 1
            spans.append(_span(f"s{counter:03d}", text, y0=y, x0=x0, x1=x1))
    return spans


def test_table_region_emits_rows_and_cells() -> None:
    """Each visual row becomes one TableRowBlock with one TableCellBlock
    per horizontally-separated span group."""
    native = NativePageV1(
        document_id="t",
        page_id="p0001",
        page_number=1,
        dimensions_pt=_DIMS,
        words=[],
        spans=_three_column_body_spans(),
        image_blocks=[],
    )
    region = Rect(x0=50, y0=190, x1=500, y1=260)
    ir = build_page_ir_real(native, table_regions=[region])

    tables = [b for b in ir.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    rows = [c for c in tables[0].children if isinstance(c, TableRowBlock)]
    assert len(rows) == 3
    for row in rows:
        assert len(row.cells) == 3, (
            f"expected 3 cells per row, got {len(row.cells)} for {row.block_id}"
        )
        for cell in row.cells:
            assert isinstance(cell, TableCellBlock)
            assert cell.children, f"cell {cell.block_id} had no inlines"

    # The flat-inline stream must still reproduce the full source text.
    flat_text = " ".join(c.text for c in iter_table_inlines(tables[0]) if hasattr(c, "text"))
    assert "BP 1" in flat_text
    assert "Search the AI deck" in flat_text


def test_heading_cell_group_refusal_emits_structured_row() -> None:
    """S5U-698 + S5U-704 — a heading line that splits into ≥2 cell groups
    now yields a ``TableBlock`` whose single child is a header
    ``TableRowBlock`` with one cell per group."""
    heading_font = "GreenleafLightPro"
    spans = [
        _span("s001", "Wounded card", y0=100.0, x0=60.0, x1=160.0, font=heading_font, size=14.0),
        _span("s002", "BP deck", y0=100.0, x0=260.0, x1=330.0, font=heading_font, size=14.0),
        _span("s003", "AI deck", y0=100.0, x0=430.0, x1=500.0, font=heading_font, size=14.0),
    ]
    native = NativePageV1(
        document_id="t",
        page_id="p0054",
        page_number=54,
        dimensions_pt=_DIMS,
        words=[],
        spans=spans,
        image_blocks=[],
    )
    ir = build_page_ir_real(native)

    tables = [b for b in ir.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    rows = [c for c in tables[0].children if isinstance(c, TableRowBlock)]
    assert len(rows) == 1
    header_row = rows[0]
    assert header_row.header is True
    assert len(header_row.cells) == 3
    cell_texts = [
        " ".join(x.text for x in cell.children if hasattr(x, "text")) for cell in header_row.cells
    ]
    assert cell_texts[0].strip().startswith("Wounded")
    assert cell_texts[1].strip() == "BP deck"
    assert cell_texts[2].strip() == "AI deck"


def test_single_column_table_region_still_emits_single_cell_row() -> None:
    """Adversarial: if a table-region row has only one cell group (narrow
    gaps, not a multi-column chart), the emitted row still wraps the
    content in a single TableCellBlock rather than silently flattening."""
    spans = [
        _span("s001", "A single-cell row", y0=200.0, x0=60.0, x1=200.0),
        _span("s002", "A second row same", y0=220.0, x0=60.0, x1=200.0),
    ]
    native = NativePageV1(
        document_id="t",
        page_id="p0001",
        page_number=1,
        dimensions_pt=_DIMS,
        words=[],
        spans=spans,
        image_blocks=[],
    )
    region = Rect(x0=50, y0=190, x1=250, y1=230)
    ir = build_page_ir_real(native, table_regions=[region])

    tables = [b for b in ir.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    rows = [c for c in tables[0].children if isinstance(c, TableRowBlock)]
    assert len(rows) == 2
    for row in rows:
        assert len(row.cells) == 1


def test_empty_heading_cell_groups_do_not_emit_empty_row() -> None:
    """Adversarial: if the heading spans are all decorative/empty after
    normalization, no TableBlock is emitted (nothing to structure)."""
    heading_font = "GreenleafLightPro"
    spans = [
        _span("s001", "  ", y0=100.0, x0=60.0, x1=70.0, font=heading_font, size=14.0),
        _span("s002", "  ", y0=100.0, x0=260.0, x1=270.0, font=heading_font, size=14.0),
    ]
    native = NativePageV1(
        document_id="t",
        page_id="p0054",
        page_number=54,
        dimensions_pt=_DIMS,
        words=[],
        spans=spans,
        image_blocks=[],
    )
    ir = build_page_ir_real(native)
    # No tables because every cell group was empty after normalization.
    tables = [b for b in ir.blocks if isinstance(b, TableBlock)]
    assert tables == []

"""S5U-734 — planner emits one TranslationSegment per TableCellBlock.

Before this fix, ``build_translation_batch`` flattened a ``TableBlock``
into a single segment via ``iter_table_inlines``, so the translator saw a
flat stream of inlines with no row/cell metadata and the downstream
re-materializer had no structure to rebuild.

This module covers the planner side of the fix:

1. Each ``TableCellBlock`` becomes one ``TranslationSegment`` whose
   ``segment_id`` is the cell's ``block_id``.
2. ``SegmentContext`` carries ``parent_block_id``, ``row_index``,
   ``cell_index``, ``is_header_row`` and ``is_header_cell`` so the
   re-materializer can group cells back into ``TableRowBlock`` rows.
3. Untranslatable cells are dropped.
4. Legacy flat ``TableBlock`` (no ``TableRowBlock`` children) still emits
   one table-level segment for back-compat.

The re-materializer side is in ``test_table_cell_rematerializer_s5u734.py``.
"""

from __future__ import annotations

from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)


def _structured_table_ir() -> PageIRV1:
    """Build a PageIRV1 whose ``TableBlock`` has structured row/cell children.

    Layout:
        header row: ["Col A", "Col B"]
        body row 1: ["1a",    "1b"]
        body row 2: ["2a",    "2b"]
    """
    rows = [
        TableRowBlock(
            block_id="tbl.r0",
            header=True,
            cells=[
                TableCellBlock(
                    block_id="tbl.r0.c0",
                    header=True,
                    children=[TextInline(text="Col A")],
                ),
                TableCellBlock(
                    block_id="tbl.r0.c1",
                    header=True,
                    children=[TextInline(text="Col B")],
                ),
            ],
        ),
        TableRowBlock(
            block_id="tbl.r1",
            cells=[
                TableCellBlock(
                    block_id="tbl.r1.c0",
                    children=[TextInline(text="1a")],
                ),
                TableCellBlock(
                    block_id="tbl.r1.c1",
                    children=[TextInline(text="1b")],
                ),
            ],
        ),
        TableRowBlock(
            block_id="tbl.r2",
            cells=[
                TableCellBlock(
                    block_id="tbl.r2.c0",
                    children=[TextInline(text="2a")],
                ),
                TableCellBlock(
                    block_id="tbl.r2.c1",
                    children=[TextInline(text="2b")],
                ),
            ],
        ),
    ]
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="blk_h",
                children=[TextInline(text="Heading")],
            ),
            TableBlock(block_id="tbl", children=rows),  # type: ignore[arg-type]
        ],
        reading_order=["blk_h", "tbl"],
    )


def _flat_table_ir() -> PageIRV1:
    """Back-compat: a TableBlock with legacy flat children (no rows)."""
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(
                block_id="flat",
                children=[TextInline(text="flat table text")],
            ),
        ],
        reading_order=["flat"],
    )


def test_planner_emits_per_cell_segment_for_structured_table() -> None:
    """Each TableCellBlock becomes its own TranslationSegment."""
    batch = build_translation_batch(_structured_table_ir())

    cell_ids = {
        "tbl.r0.c0",
        "tbl.r0.c1",
        "tbl.r1.c0",
        "tbl.r1.c1",
        "tbl.r2.c0",
        "tbl.r2.c1",
    }
    seg_ids = {s.segment_id for s in batch.segments}
    assert cell_ids.issubset(seg_ids), f"expected per-cell segments {cell_ids}, got {seg_ids}"
    assert "tbl" not in seg_ids, "structured TableBlock must not emit a table-level segment"


def test_planner_per_cell_segment_carries_row_cell_context() -> None:
    """SegmentContext carries parent table block_id, row_index, cell_index,
    header flags so the re-materializer can stitch cells back into rows."""
    batch = build_translation_batch(_structured_table_ir())

    r0c0 = next(s for s in batch.segments if s.segment_id == "tbl.r0.c0")
    r1c1 = next(s for s in batch.segments if s.segment_id == "tbl.r1.c1")
    r2c0 = next(s for s in batch.segments if s.segment_id == "tbl.r2.c0")

    assert r0c0.block_type == "table_cell"
    assert r0c0.context.parent_block_id == "tbl"
    assert r0c0.context.row_index == 0
    assert r0c0.context.cell_index == 0
    assert r0c0.context.is_header_row is True
    assert r0c0.context.is_header_cell is True

    assert r1c1.context.row_index == 1
    assert r1c1.context.cell_index == 1
    assert r1c1.context.is_header_row is False
    assert r1c1.context.is_header_cell is False

    assert r2c0.context.row_index == 2
    assert r2c0.context.cell_index == 0


def test_planner_per_cell_segment_source_inline_is_cell_inlines_only() -> None:
    """Each cell segment's source_inline is exactly the cell's children —
    not the concatenation of every cell in the table."""
    batch = build_translation_batch(_structured_table_ir())

    r0c0 = next(s for s in batch.segments if s.segment_id == "tbl.r0.c0")
    texts = [n.text for n in r0c0.source_inline if hasattr(n, "text")]
    assert texts == ["Col A"]

    r2c1 = next(s for s in batch.segments if s.segment_id == "tbl.r2.c1")
    texts2 = [n.text for n in r2c1.source_inline if hasattr(n, "text")]
    assert texts2 == ["2b"]


def test_planner_skips_untranslatable_cells() -> None:
    """A cell with ``translatable=False`` is dropped from the batch."""
    ir = _structured_table_ir()
    tbl = ir.blocks[1]
    assert isinstance(tbl, TableBlock)
    row0 = tbl.children[0]
    assert isinstance(row0, TableRowBlock)
    row0.cells[0].translatable = False

    batch = build_translation_batch(ir)
    seg_ids = {s.segment_id for s in batch.segments}
    assert "tbl.r0.c0" not in seg_ids
    assert "tbl.r0.c1" in seg_ids


def test_planner_falls_back_to_table_segment_for_flat_table() -> None:
    """Legacy flat TableBlock (no TableRowBlock children) still emits one
    table-level segment for back-compat."""
    batch = build_translation_batch(_flat_table_ir())
    seg_ids = {s.segment_id for s in batch.segments}
    assert seg_ids == {"flat"}
    seg = batch.segments[0]
    assert seg.block_type == "table"

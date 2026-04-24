"""S5U-734 — per-cell translation segments for structured TableBlocks.

The planner previously flattened a ``TableBlock`` into a **single** segment
via ``iter_table_inlines``; downstream, the re-materializer rebuilt only the
flat ``children`` of the RU ``TableBlock``, so row/cell boundaries vanished.

This module covers the fix:

1. The planner emits one ``TranslationSegment`` per ``TableCellBlock`` when
   the source ``TableBlock`` has structured row/cell children, with the
   cell's ``block_id`` as segment id and row/cell/header metadata in
   ``SegmentContext``.
2. Legacy flat ``TableBlock`` (no ``TableRowBlock`` children) still emits
   one table-level segment (back-compat with cached artifacts).
3. The re-materializer groups per-cell translated segments back into a
   structured RU ``TableBlock`` with ``TableRowBlock`` / ``TableCellBlock``
   mirroring the EN source.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)
from atr_schemas.source_manifest_v1 import SourceManifestV1
from atr_schemas.translation_result_v1 import (
    TranslatedSegment,
    TranslationResultV1,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


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


# --- Planner tests ---


def test_planner_emits_per_cell_segment_for_structured_table() -> None:
    """Each TableCellBlock becomes its own TranslationSegment."""
    batch = build_translation_batch(_structured_table_ir())

    # One segment per cell (6) + heading (1). The table itself does NOT
    # produce a table-level segment when it's structured.
    cell_ids = {
        "tbl.r0.c0",
        "tbl.r0.c1",
        "tbl.r1.c0",
        "tbl.r1.c1",
        "tbl.r2.c0",
        "tbl.r2.c1",
    }
    seg_ids = {s.segment_id for s in batch.segments}
    assert cell_ids.issubset(seg_ids), (
        f"expected per-cell segments {cell_ids}, got {seg_ids}"
    )
    assert "tbl" not in seg_ids, (
        "structured TableBlock must not emit a table-level segment"
    )


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
    # Mark one cell as not translatable.
    tbl = ir.blocks[1]
    assert isinstance(tbl, TableBlock)
    row0 = tbl.children[0]
    assert isinstance(row0, TableRowBlock)
    row0.cells[0].translatable = False

    batch = build_translation_batch(ir)
    seg_ids = {s.segment_id for s in batch.segments}
    assert "tbl.r0.c0" not in seg_ids
    # Others still emitted.
    assert "tbl.r0.c1" in seg_ids


def test_planner_falls_back_to_table_segment_for_flat_table() -> None:
    """Legacy flat TableBlock (no TableRowBlock children) still emits one
    table-level segment for back-compat."""
    batch = build_translation_batch(_flat_table_ir())
    seg_ids = {s.segment_id for s in batch.segments}
    assert seg_ids == {"flat"}
    seg = batch.segments[0]
    assert seg.block_type == "table"


# --- Re-materializer tests (run via full TranslationStage) ---


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="test_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="test_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_prerequisites(ctx: StageContext) -> None:
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success
    r = execute_stage(SymbolsStage(), ctx)
    assert r.success
    r = execute_stage(StructureStage(), ctx)
    assert r.success


def _inject_structured_table_en_ir(ctx: StageContext) -> None:
    """Overwrite p0001's EN IR with one that has a structured TableBlock
    (heading + 2×2 body) so the re-materializer has something to stitch."""
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p",
                children=[TextInline(text="intro paragraph")],
            ),
            TableBlock(
                block_id="t",
                children=[  # type: ignore[arg-type]
                    TableRowBlock(
                        block_id="t.r0",
                        header=True,
                        cells=[
                            TableCellBlock(
                                block_id="t.r0.c0",
                                header=True,
                                children=[TextInline(text="H1")],
                            ),
                            TableCellBlock(
                                block_id="t.r0.c1",
                                header=True,
                                children=[TextInline(text="H2")],
                            ),
                        ],
                    ),
                    TableRowBlock(
                        block_id="t.r1",
                        cells=[
                            TableCellBlock(
                                block_id="t.r1.c0",
                                children=[TextInline(text="A1")],
                            ),
                            TableCellBlock(
                                block_id="t.r1.c1",
                                children=[TextInline(text="A2")],
                            ),
                        ],
                    ),
                ],
            ),
        ],
        reading_order=["p", "t"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=ir,
    )


def test_rematerializer_preserves_row_cell_structure(tmp_path: Path) -> None:
    """RU TableBlock has the same row/cell structure as the EN source."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    _inject_structured_table_en_ir(ctx)

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    ru_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.ru",
        scope="page",
        entity_id="p0001",
    )
    assert ru_data is not None
    ru_ir = PageIRV1.model_validate(ru_data)

    tables = [b for b in ru_ir.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1, "RU page should have exactly one TableBlock"
    tbl = tables[0]
    assert tbl.block_id == "t"

    rows = [c for c in tbl.children if isinstance(c, TableRowBlock)]
    assert len(rows) == 2, (
        f"expected 2 rows in RU table, got {len(rows)} — "
        "S5U-734 gap: re-materializer flattened structure"
    )
    assert rows[0].block_id == "t.r0"
    assert rows[0].header is True
    assert len(rows[0].cells) == 2
    assert rows[0].cells[0].block_id == "t.r0.c0"
    assert rows[0].cells[0].header is True

    assert rows[1].block_id == "t.r1"
    assert rows[1].header is False
    assert len(rows[1].cells) == 2
    assert rows[1].cells[1].block_id == "t.r1.c1"


def test_rematerializer_handles_missing_cell_translation(tmp_path: Path) -> None:
    """If a cell translation is missing, the re-materializer keeps the row
    structure and leaves that cell empty rather than collapsing the row."""
    # This is a property-level test: stub a minimal translator that only
    # translates part of the batch. We exercise the stage's re-materializer
    # behavior directly by constructing the inputs.
    from atr_pipeline.stages.translation.stage import _rematerialize_ru_blocks

    en_ir = PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(
                block_id="t",
                children=[  # type: ignore[arg-type]
                    TableRowBlock(
                        block_id="t.r0",
                        cells=[
                            TableCellBlock(
                                block_id="t.r0.c0",
                                children=[TextInline(text="A")],
                            ),
                            TableCellBlock(
                                block_id="t.r0.c1",
                                children=[TextInline(text="B")],
                            ),
                        ],
                    ),
                ],
            ),
        ],
        reading_order=["t"],
    )
    # Only the first cell translated.
    result = TranslationResultV1(
        batch_id="b",
        segments=[
            TranslatedSegment(
                segment_id="t.r0.c0",
                target_inline=[TextInline(text="А", lang=LanguageCode.RU)],
            ),
        ],
    )
    batch = build_translation_batch(en_ir)

    ru_blocks = _rematerialize_ru_blocks(en_ir, batch, result)
    tables = [b for b in ru_blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    rows = [c for c in tables[0].children if isinstance(c, TableRowBlock)]
    assert len(rows) == 1
    assert len(rows[0].cells) == 2
    # c0 translated, c1 empty but structurally present
    c0_texts = [n.text for n in rows[0].cells[0].children if hasattr(n, "text")]
    assert c0_texts == ["А"]
    c1_texts = [n.text for n in rows[0].cells[1].children if hasattr(n, "text")]
    assert c1_texts == []  # no translation arrived, cell empty


def test_rematerializer_flat_table_still_emits_flat_table() -> None:
    """Back-compat: a flat (legacy) TableBlock in EN yields a flat RU table."""
    from atr_pipeline.stages.translation.stage import _rematerialize_ru_blocks

    en_ir = _flat_table_ir()
    result = TranslationResultV1(
        batch_id="b",
        segments=[
            TranslatedSegment(
                segment_id="flat",
                target_inline=[TextInline(text="плоская", lang=LanguageCode.RU)],
            ),
        ],
    )
    batch = build_translation_batch(en_ir)

    ru_blocks = _rematerialize_ru_blocks(en_ir, batch, result)
    tables = [b for b in ru_blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    tbl = tables[0]
    # No TableRowBlock — just flat inlines
    rows = [c for c in tbl.children if isinstance(c, TableRowBlock)]
    assert rows == []
    flat_texts = [c.text for c in tbl.children if hasattr(c, "text")]
    assert flat_texts == ["плоская"]

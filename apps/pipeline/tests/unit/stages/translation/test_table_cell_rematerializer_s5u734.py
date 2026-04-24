"""S5U-734 — RU re-materializer tests for per-cell TableBlock translation.

Complements ``test_table_cell_segments_s5u734.py`` (planner-level tests) by
exercising ``_rematerialize_ru_blocks`` and the full ``TranslationStage`` on
pages with structured ``TableBlock`` IR.
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
from atr_pipeline.stages.translation.stage import (
    TranslationStage,
    _rematerialize_ru_blocks,
)
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
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
    """Overwrite p0001's EN IR with one that has a structured TableBlock.

    Layout: one header row + one body row, 2 cells wide.
    """
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


def _flat_table_ir() -> PageIRV1:
    """Legacy flat TableBlock (no TableRowBlock children)."""
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


def test_rematerializer_handles_missing_cell_translation() -> None:
    """If a cell translation is missing, the re-materializer keeps the row
    structure and leaves that cell empty rather than collapsing the row."""
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
                target_inline=[TextInline(text="ru-A", lang=LanguageCode.RU)],
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
    assert c0_texts == ["ru-A"]
    c1_texts = [n.text for n in rows[0].cells[1].children if hasattr(n, "text")]
    assert c1_texts == []  # no translation arrived, cell empty


def test_rematerializer_flat_table_still_emits_flat_table() -> None:
    """Back-compat: a flat (legacy) TableBlock in EN yields a flat RU table."""
    en_ir = _flat_table_ir()
    result = TranslationResultV1(
        batch_id="b",
        segments=[
            TranslatedSegment(
                segment_id="flat",
                target_inline=[TextInline(text="ru-flat", lang=LanguageCode.RU)],
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
    assert flat_texts == ["ru-flat"]

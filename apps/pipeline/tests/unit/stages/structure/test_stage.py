"""Tests for the Structure stage."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.structure.stage import StructureResult, StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
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
    """Run ingest → extract_native → symbols."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))

    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success

    r = execute_stage(SymbolsStage(), ctx)
    assert r.success


def test_structure_implements_stage_protocol() -> None:
    """StructureStage satisfies the Stage protocol."""
    stage = StructureStage()
    assert isinstance(stage, Stage)
    assert stage.name == "structure"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_structure_builds_ir(tmp_path: Path) -> None:
    """StructureStage builds page IR after full prerequisite chain."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(StructureStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    structure_result = StructureResult.model_validate(data)
    assert structure_result.document_id == "walking_skeleton"
    assert structure_result.pages_built == 1
    assert structure_result.total_blocks > 0

    # Verify per-page artifact was stored
    ir_dir = tmp_path / "artifacts" / "walking_skeleton" / "page_ir.v1.en" / "page" / "p0001"
    assert ir_dir.exists()
    jsons = list(ir_dir.glob("*.json"))
    assert len(jsons) == 1


def test_structure_raises_without_native_pages(tmp_path: Path) -> None:
    """StructureStage fails when no native pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(StructureStage(), ctx)
    assert not result.success
    assert "Run extract_native first" in (result.error or "")

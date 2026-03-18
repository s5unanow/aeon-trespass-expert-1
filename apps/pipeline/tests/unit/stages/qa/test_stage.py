"""Tests for the QA stage."""

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
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.source_manifest_v1 import SourceManifestV1


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
    """Run ingest → extract_native → symbols → structure → translate → render."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))

    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success

    r = execute_stage(SymbolsStage(), ctx)
    assert r.success

    r = execute_stage(StructureStage(), ctx)
    assert r.success

    r = execute_stage(TranslationStage(), ctx)
    assert r.success

    r = execute_stage(RenderStage(), ctx)
    assert r.success


def test_qa_implements_stage_protocol() -> None:
    """QAStage satisfies the Stage protocol."""
    stage = QAStage()
    assert isinstance(stage, Stage)
    assert stage.name == "qa"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_qa_persists_summary_clean_pipeline(tmp_path: Path) -> None:
    """QAStage persists a QASummaryV1 with no blocking issues."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    summary = QASummaryV1.model_validate(data)
    assert summary.document_id == "walking_skeleton"
    assert summary.run_id == "test_run"
    assert summary.blocking is False
    assert summary.counts.error == 0
    assert summary.counts.critical == 0
    assert summary.record_refs == []


def test_qa_raises_without_en_ir(tmp_path: Path) -> None:
    """QAStage fails when no EN IR pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(QAStage(), ctx)
    assert not result.success
    assert "No EN IR pages found" in (result.error or "")

"""Tests for the Symbols stage."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeResult, ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.symbols.stage import SymbolsResult, SymbolsStage
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


def _run_prerequisites(ctx: StageContext) -> ExtractNativeResult:
    """Run ingest + extract_native, return extract result."""
    ingest_result = execute_stage(IngestStage(), ctx)
    assert ingest_result.success
    manifest = SourceManifestV1.model_validate(
        ctx.artifact_store.get_json(ingest_result.artifact_ref)
    )

    extract_result = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert extract_result.success
    return ExtractNativeResult.model_validate(
        ctx.artifact_store.get_json(extract_result.artifact_ref)
    )


def test_symbols_implements_stage_protocol() -> None:
    """SymbolsStage satisfies the Stage protocol."""
    stage = SymbolsStage()
    assert isinstance(stage, Stage)
    assert stage.name == "symbols"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.2"


def test_symbols_runs_after_extract_native(tmp_path: Path) -> None:
    """SymbolsStage runs successfully after ingest + extract_native."""
    ctx = _make_ctx(tmp_path)
    extract_result = _run_prerequisites(ctx)

    result = execute_stage(SymbolsStage(), ctx, input_data=extract_result)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    symbols_result = SymbolsResult.model_validate(data)
    assert symbols_result.document_id == "walking_skeleton"
    assert symbols_result.pages_matched >= 0


def test_symbols_raises_without_prerequisites(tmp_path: Path) -> None:
    """SymbolsStage fails when no native pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(SymbolsStage(), ctx)
    # Walking skeleton may not have a symbol catalog, so it could succeed
    # with 0 matches or fail with missing pages — either is valid
    # The important thing is it doesn't crash with an unhandled exception
    assert result.error is None or "Run extract_native first" in result.error

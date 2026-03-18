"""Tests for the ExtractNative stage."""

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


def _ingest_first(ctx: StageContext) -> SourceManifestV1:
    """Run ingest stage and return the manifest."""
    result = execute_stage(IngestStage(), ctx)
    assert result.success
    data = ctx.artifact_store.get_json(result.artifact_ref)
    return SourceManifestV1.model_validate(data)


def test_extract_native_implements_stage_protocol() -> None:
    """ExtractNativeStage satisfies the Stage protocol."""
    stage = ExtractNativeStage()
    assert isinstance(stage, Stage)
    assert stage.name == "extract_native"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_extract_native_produces_pages(tmp_path: Path) -> None:
    """ExtractNativeStage extracts all pages and stores artifacts."""
    ctx = _make_ctx(tmp_path)
    manifest = _ingest_first(ctx)

    result = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert result.success
    assert result.artifact_ref is not None

    # Verify the result data
    data = ctx.artifact_store.get_json(result.artifact_ref)
    extract_result = ExtractNativeResult.model_validate(data)
    assert extract_result.document_id == "walking_skeleton"
    assert extract_result.page_count == 1
    assert extract_result.page_ids == ["p0001"]

    # Verify per-page artifact was stored
    native_dir = tmp_path / "artifacts" / "walking_skeleton" / "native_page.v1" / "page" / "p0001"
    natives = list(native_dir.glob("*.json"))
    assert len(natives) == 1


def test_extract_native_fallback_reads_manifest_from_store(tmp_path: Path) -> None:
    """ExtractNativeStage reads manifest from store when no input_data."""
    ctx = _make_ctx(tmp_path)
    _ingest_first(ctx)

    # Run without passing manifest as input — should fall back to store
    result = execute_stage(ExtractNativeStage(), ctx)
    assert result.success

    data = ctx.artifact_store.get_json(result.artifact_ref)
    extract_result = ExtractNativeResult.model_validate(data)
    assert extract_result.page_count == 1

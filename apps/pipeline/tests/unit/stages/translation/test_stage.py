"""Tests for the Translation stage."""

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
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationResult, TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    # Use mock translator so tests don't hit real APIs
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
    """Run ingest → extract_native → symbols → structure."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))

    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success

    r = execute_stage(SymbolsStage(), ctx)
    assert r.success

    r = execute_stage(StructureStage(), ctx)
    assert r.success


def test_translation_implements_stage_protocol() -> None:
    """TranslationStage satisfies the Stage protocol."""
    stage = TranslationStage()
    assert isinstance(stage, Stage)
    assert stage.name == "translate"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_translation_translates_pages(tmp_path: Path) -> None:
    """TranslationStage produces RU IR after full prerequisite chain."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(TranslationStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    tr_result = TranslationResult.model_validate(data)
    assert tr_result.document_id == "walking_skeleton"
    assert tr_result.pages_translated == 1

    # Verify per-page RU IR artifact was stored
    ru_dir = tmp_path / "artifacts" / "walking_skeleton" / "page_ir.v1.ru" / "page" / "p0001"
    assert ru_dir.exists()
    jsons = list(ru_dir.glob("*.json"))
    assert len(jsons) == 1


def test_translation_persists_metadata(tmp_path: Path) -> None:
    """TranslationStage stores translation_meta.v1 with provenance fields."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    # Verify translation metadata artifact was stored
    meta_dir = (
        tmp_path / "artifacts" / "walking_skeleton" / "translation_meta.v1" / "page" / "p0001"
    )
    assert meta_dir.exists()
    jsons = list(meta_dir.glob("*.json"))
    assert len(jsons) == 1

    import json

    meta = json.loads(jsons[0].read_text())
    assert meta["provider"] == "mock"
    assert meta["model"] == "mock-v1"
    assert meta["prompt_profile"] == "translate_rules_ru.v1"
    assert meta["page_id"] == "p0001"
    assert "source_checksums" in meta
    assert len(meta["source_checksums"]) > 0
    # Each checksum should be a 12-char hex string
    for checksum in meta["source_checksums"].values():
        assert len(checksum) == 12


def test_translation_raises_without_en_ir(tmp_path: Path) -> None:
    """TranslationStage fails when no EN IR pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(TranslationStage(), ctx)
    assert not result.success
    assert "Run structure stage first" in (result.error or "")

"""Tests for RunManifestV1 assembly from registry data."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, get_run, start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.manifest_builder import build_run_manifest
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.run_manifest_v1 import RunManifestV1
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    cfg_hash = content_hash(config.model_dump(mode="json"))
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="test_manifest_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash=cfg_hash,
    )
    return StageContext(
        run_id="test_manifest_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_build_manifest_after_two_stages(tmp_path: Path) -> None:
    """Manifest contains stage invocation refs for all executed stages."""
    ctx = _make_ctx(tmp_path)

    r1 = execute_stage(IngestStage(), ctx)
    assert r1.success
    manifest_data = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r1.artifact_ref))

    r2 = execute_stage(ExtractNativeStage(), ctx, input_data=manifest_data)
    assert r2.success

    finish_run(ctx.registry_conn, run_id="test_manifest_run", status="completed")

    manifest = build_run_manifest(ctx.registry_conn, run_id="test_manifest_run")
    assert isinstance(manifest, RunManifestV1)
    assert manifest.run_id == "test_manifest_run"
    assert manifest.pipeline_version == "0.1.0"
    assert len(manifest.stages) == 2
    assert manifest.stages[0].stage_name == "ingest"
    assert manifest.stages[0].status == "completed"
    assert manifest.stages[0].artifact_ref != ""
    assert manifest.stages[1].stage_name == "extract_native"
    assert manifest.stages[1].status == "completed"
    assert manifest.stages[1].artifact_ref != ""


def test_manifest_has_config_hash(tmp_path: Path) -> None:
    """Manifest records the config hash from the run record."""
    ctx = _make_ctx(tmp_path)
    execute_stage(IngestStage(), ctx)
    finish_run(ctx.registry_conn, run_id="test_manifest_run", status="completed")

    manifest = build_run_manifest(ctx.registry_conn, run_id="test_manifest_run")
    assert manifest.config_hash != ""
    assert len(manifest.config_hash) == 12


def test_manifest_has_git_commit(tmp_path: Path) -> None:
    """Manifest captures a non-empty git commit SHA (when in a repo)."""
    ctx = _make_ctx(tmp_path)
    execute_stage(IngestStage(), ctx)
    finish_run(ctx.registry_conn, run_id="test_manifest_run", status="completed")

    manifest = build_run_manifest(ctx.registry_conn, run_id="test_manifest_run")
    # We're running inside a git repo, so this should be non-empty
    assert manifest.git_commit != ""
    assert len(manifest.git_commit) == 40


def test_manifest_persisted_as_artifact(tmp_path: Path) -> None:
    """Manifest can be persisted to artifact store and loaded back."""
    ctx = _make_ctx(tmp_path)
    execute_stage(IngestStage(), ctx)
    finish_run(ctx.registry_conn, run_id="test_manifest_run", status="completed")

    manifest = build_run_manifest(ctx.registry_conn, run_id="test_manifest_run")
    ref = ctx.artifact_store.put_json(
        document_id="walking_skeleton",
        schema_family="run_manifest.v1",
        scope="run",
        entity_id="test_manifest_run",
        data=manifest,
    )

    loaded = ctx.artifact_store.get_json(ref)
    roundtrip = RunManifestV1.model_validate(loaded)
    assert roundtrip.run_id == manifest.run_id
    assert len(roundtrip.stages) == len(manifest.stages)


def test_manifest_ref_stored_on_run(tmp_path: Path) -> None:
    """run_manifest_ref is stored on the runs table."""
    from atr_pipeline.registry.runs import set_run_manifest_ref

    ctx = _make_ctx(tmp_path)
    execute_stage(IngestStage(), ctx)
    finish_run(ctx.registry_conn, run_id="test_manifest_run", status="completed")

    manifest = build_run_manifest(ctx.registry_conn, run_id="test_manifest_run")
    ref = ctx.artifact_store.put_json(
        document_id="walking_skeleton",
        schema_family="run_manifest.v1",
        scope="run",
        entity_id="test_manifest_run",
        data=manifest,
    )
    set_run_manifest_ref(ctx.registry_conn, run_id="test_manifest_run", ref=ref.relative_path)

    run = get_run(ctx.registry_conn, "test_manifest_run")
    assert run is not None
    assert run["run_manifest_ref"] == ref.relative_path

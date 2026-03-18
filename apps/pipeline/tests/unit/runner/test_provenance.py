"""Tests for provenance: config hashes and stage events are persisted."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run, start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _make_ctx(tmp_path: Path, *, config_hash: str = "") -> tuple[StageContext, str]:
    """Create a test StageContext with a real config hash. Returns (ctx, config_hash)."""
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    cfg_hash = config_hash or content_hash(config.model_dump(mode="json"))
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    run_id = "test_provenance_run"
    start_run(
        conn,
        run_id=run_id,
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash=cfg_hash,
    )
    ctx = StageContext(
        run_id=run_id,
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )
    return ctx, cfg_hash


def test_run_record_has_real_config_hash(tmp_path: Path) -> None:
    """Run record stores a non-empty config hash derived from the config."""
    ctx, cfg_hash = _make_ctx(tmp_path)

    assert cfg_hash != ""
    assert len(cfg_hash) == 12

    run = get_run(ctx.registry_conn, "test_provenance_run")
    assert run is not None
    assert run["config_hash"] == cfg_hash


def test_stage_events_emitted_on_execution(tmp_path: Path) -> None:
    """Stage events are written for each executed stage."""
    ctx, _ = _make_ctx(tmp_path)

    result = execute_stage(IngestStage(), ctx)
    assert result.success

    events = list_stage_events(ctx.registry_conn, run_id="test_provenance_run")
    assert len(events) == 1

    event = events[0]
    assert event["stage_name"] == "ingest"
    assert event["scope"] == "document"
    assert event["entity_id"] == "walking_skeleton"
    assert event["status"] == "completed"
    assert event["cache_key"] != ""
    assert len(event["cache_key"]) == 12
    assert event["artifact_ref"] is not None
    assert event["duration_ms"] is not None
    assert event["duration_ms"] >= 0
    assert event["error_message"] is None


def test_stage_events_for_multi_stage_run(tmp_path: Path) -> None:
    """Multiple stages produce one event each with correct provenance."""
    ctx, _ = _make_ctx(tmp_path)

    r1 = execute_stage(IngestStage(), ctx)
    assert r1.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r1.artifact_ref))

    r2 = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r2.success

    events = list_stage_events(ctx.registry_conn, run_id="test_provenance_run")
    assert len(events) == 2

    assert events[0]["stage_name"] == "ingest"
    assert events[1]["stage_name"] == "extract_native"

    # Each event has a unique cache key (different stages)
    assert events[0]["cache_key"] != events[1]["cache_key"]

    # Both completed successfully
    for ev in events:
        assert ev["status"] == "completed"
        assert ev["artifact_ref"] is not None
        assert ev["duration_ms"] >= 0


def test_failed_stage_event_records_error(tmp_path: Path) -> None:
    """A failed stage records the error message in the event."""
    ctx, _ = _make_ctx(tmp_path)

    # Run structure stage without prerequisites — will fail
    from atr_pipeline.stages.structure.stage import StructureStage

    result = execute_stage(StructureStage(), ctx)
    assert not result.success

    events = list_stage_events(ctx.registry_conn, run_id="test_provenance_run")
    assert len(events) == 1
    assert events[0]["status"] == "failed"
    assert events[0]["error_message"] is not None
    assert "Run extract_native first" in events[0]["error_message"]


def test_cached_stage_skips_event(tmp_path: Path) -> None:
    """A cache hit does not create a new stage event."""
    ctx, _ = _make_ctx(tmp_path)

    r1 = execute_stage(IngestStage(), ctx)
    assert r1.success
    assert not r1.cached

    r2 = execute_stage(IngestStage(), ctx)
    assert r2.success
    assert r2.cached

    # Only one event — the cache hit did not write a new one
    events = list_stage_events(ctx.registry_conn, run_id="test_provenance_run")
    assert len(events) == 1

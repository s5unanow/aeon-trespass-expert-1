"""Tests for the Publish stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.publish.qa_gate import QAGateError
from atr_pipeline.stages.publish.stage import (
    PublishResult,
    PublishStage,
    _load_qa_summary_from_registry,
)
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity, StageScope
from atr_schemas.qa_record_v1 import QARecordV1
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
    """Run ingest → ... → qa."""
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

    r = execute_stage(QAStage(), ctx)
    assert r.success


def test_publish_implements_stage_protocol() -> None:
    """PublishStage satisfies the Stage protocol."""
    stage = PublishStage()
    assert isinstance(stage, Stage)
    assert stage.name == "publish"
    assert stage.scope == StageScope.DOCUMENT
    # S5U-870 — bumped 1.0 -> 1.1 when the blocking-QA gate landed.
    assert stage.version == "1.1"


def test_publish_builds_release_bundle(tmp_path: Path) -> None:
    """PublishStage creates a release bundle after full pipeline."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(PublishStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    publish_result = PublishResult.model_validate(data)
    assert publish_result.document_id == "walking_skeleton"
    assert publish_result.build_id != ""
    assert publish_result.files_published >= 1

    # Verify release directory with edition subdirectory was created
    release_dir = tmp_path / "artifacts" / "walking_skeleton" / "release"
    assert release_dir.exists()
    # Default edition is "ru" for full pipeline (translation included)
    edition_dir = release_dir / "ru"
    assert (edition_dir / "manifest.json").exists()
    assert (edition_dir / "data").exists()


# --- S5U-870 blocking-QA gate ------------------------------------------------


def _blocking_record(code: str, page_id: str) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{code}.{page_id}",
        layer=QALayer.STRUCTURE,
        severity=Severity.ERROR,
        code=code,
        page_id=page_id,
        waived=False,
    )


def _seed_qa_summary(ctx: StageContext, summary: QASummaryV1) -> None:
    """Write a QASummaryV1 artifact + a 'qa' stage event for the run.

    Lets the publish gate resolve a synthetic (e.g. blocking) QA summary
    without needing the document's real QA to be blocking. Records referenced
    by ``summary.record_refs`` are presumed already written by the caller.
    """
    ref = ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="qa",
        scope="document",
        entity_id=ctx.document_id,
        data=summary,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name="qa",
        scope="document",
        entity_id=ctx.document_id,
        cache_key=f"seed_qa_{ctx.run_id}",
    )
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=ref.relative_path,
    )


def _seed_blocking_summary(ctx: StageContext) -> QASummaryV1:
    """Seed a blocking QA summary with one named blocking record. Returns it."""
    rec = _blocking_record("GLUED_TEXT", "p0007")
    rec_ref = ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="qa_record.v1",
        scope="page",
        entity_id="p0007",
        data=rec,
    )
    summary = QASummaryV1(
        document_id=ctx.document_id,
        run_id=ctx.run_id,
        blocking=True,
        record_refs=[rec_ref.relative_path],
        review_pack_ref="walking_skeleton/review_pack.v1/document/walking_skeleton/rp.json",
    )
    _seed_qa_summary(ctx, summary)
    return summary


def test_publish_refuses_on_blocking_qa(tmp_path: Path) -> None:
    """Default mode: blocking, non-waived QA refuses the publish, naming codes/pages.

    Red-before: at 2b078bc PublishStage has no gate — the stage would succeed
    and build the bundle. With the gate, ``run()`` raises QAGateError so
    ``execute_stage`` records the stage as failed (no bundle written).
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    _seed_blocking_summary(ctx)

    # Direct run() raises with a code/page-naming message.
    with pytest.raises(QAGateError) as exc:
        PublishStage().run(ctx, None)
    assert "GLUED_TEXT" in str(exc.value)
    assert "p0007" in str(exc.value)

    # Via the executor the failure is recorded; no completed publish artifact.
    result = execute_stage(PublishStage(), ctx)
    assert not result.success
    assert result.artifact_ref is None


def test_publish_review_only_produces_draft(tmp_path: Path) -> None:
    """--review-only (publish_review_only=True) builds a draft over blocking QA.

    Red-before: at 2b078bc there is no publish_review_only field and no draft
    concept — PublishResult has no review_only/blocking fields to assert.
    """
    ctx = _make_ctx(tmp_path)
    ctx.publish_review_only = True
    _run_prerequisites(ctx)
    _seed_blocking_summary(ctx)

    result = PublishStage().run(ctx, None)
    assert result.review_only is True
    assert result.blocking is True
    assert result.files_published >= 1


def test_publish_review_only_does_not_flip_for_non_blocking(tmp_path: Path) -> None:
    """A non-blocking run is never marked a draft even with review_only set.

    Red-before: PublishResult had no review_only/blocking fields at 2b078bc.
    """
    ctx = _make_ctx(tmp_path)
    ctx.publish_review_only = True
    _run_prerequisites(ctx)

    result = PublishStage().run(ctx, None)
    assert result.blocking is False
    assert result.review_only is True  # flag echoed, but...
    # ...is_draft is False because the run is not blocking (asserted via fields).
    assert not (result.blocking and result.review_only)


def test_publish_fails_closed_when_no_qa_summary(tmp_path: Path) -> None:
    """G1: a run with render but no QA stage event refuses (not pass-by-absent).

    Red-before: at 2b078bc PublishStage ignores QA entirely and would publish.
    """
    ctx = _make_ctx(tmp_path)
    # Run only up to render — skip QA so no qa stage event exists.
    r = execute_stage(IngestStage(), ctx)
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    execute_stage(SymbolsStage(), ctx)
    execute_stage(StructureStage(), ctx)
    execute_stage(TranslationStage(), ctx)
    execute_stage(RenderStage(), ctx)

    assert _load_qa_summary_from_registry(ctx) is None
    with pytest.raises(QAGateError, match="no QA summary"):
        PublishStage().run(ctx, None)


def test_publish_cache_hit_does_not_serve_stale_pass_on_blocking(tmp_path: Path) -> None:
    """S5U-662: a blocking run can never be served from a cached 'publish succeeded'.

    Publish succeeds once on the (non-blocking) walking_skeleton run, caching a
    completed publish event under version 1.1. We then seed a blocking QA
    summary for the SAME run and re-execute: the gate must still refuse — a
    refusal raises before any artifact write, so the blocking case is never
    cached and cannot short-circuit the gate.

    Red-before: at 2b078bc there is no gate, so a second execute_stage would
    serve the cached pass regardless of QA.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    first = execute_stage(PublishStage(), ctx)
    assert first.success  # non-blocking → cached pass under v1.1

    # Now the run becomes blocking (a new blocking QA summary is the run's QA).
    _seed_blocking_summary(ctx)
    second = execute_stage(PublishStage(), ctx)
    assert not second.success  # gate refuses; the cached pass is NOT served

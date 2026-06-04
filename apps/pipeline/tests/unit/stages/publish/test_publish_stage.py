"""Tests for the Publish stage (blocking-QA gate behavior).

The S5U-894 on-disk draft-label tests live in ``test_publish_draft_label.py``;
shared fixtures (context builder, prerequisite runner, blocking-summary seeder)
live in ``_publish_fixtures.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.publish.qa_gate import QAGateError
from atr_pipeline.stages.publish.stage import (
    PublishResult,
    PublishStage,
    _load_qa_summary_from_registry,
)
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1

from ._publish_fixtures import (
    make_ctx as _make_ctx,
)
from ._publish_fixtures import (
    run_prerequisites as _run_prerequisites,
)
from ._publish_fixtures import (
    seed_blocking_summary as _seed_blocking_summary,
)


def test_publish_implements_stage_protocol() -> None:
    """PublishStage satisfies the Stage protocol."""
    stage = PublishStage()
    assert isinstance(stage, Stage)
    assert stage.name == "publish"
    assert stage.scope == StageScope.DOCUMENT
    # S5U-870 — bumped 1.0 -> 1.1 when the blocking-QA gate landed.
    # S5U-894 — bumped 1.1 -> 1.2 when the draft label was stamped into the
    # on-disk BuildManifestV1 (new persisted side-effect of run()).
    assert stage.version == "1.2"


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
    completed publish event under the current stage version. We then seed a
    blocking QA summary for the SAME run and re-execute: the gate must still
    refuse — a
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

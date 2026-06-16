"""S5U-1227 — ExtractLayoutStage cache-hit replay regression.

Per ``.claude/rules/pipeline.md`` § "Stage-output cache invalidation": when a
stage's summary changes observable shape (here ``ExtractLayoutResult`` gains the
content-bearing ``page_refs`` field, replacing the count-only summary) the
stage's ``version`` field MUST be bumped (done: 1.2 -> 1.3) **AND** a regression
test must exercise the executor's cache-hit path to assert the side-effect is
preserved on cached runs.

This test runs ``ExtractLayoutStage`` twice via the executor and asserts every
persisted artifact from the first run remains on disk byte-identical after the
second (cache-hit) run.

Guarded schema families:

* ``extract_layout`` — the executor-written summary artifact
  (``ExtractLayoutResult``), which now carries ``page_refs``.
* ``layout_page.v1`` — the per-page artifacts ``page_refs`` indexes.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_layout.stage import ExtractLayoutStage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1
from tests.unit.stages.qa.test_stage_cache_hit import (
    assert_cache_hit_replays_artifact,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="extract_layout_cache_hit_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="extract_layout_cache_hit_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_prerequisites_excluding_extract_layout(ctx: StageContext) -> None:
    """ingest -> extract_native (NOT extract_layout)."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success


def test_extract_layout_stage_cache_hit_preserves_artifacts(tmp_path: Path) -> None:
    """Second ``execute_stage(ExtractLayoutStage(), ctx)`` must hit the cache
    and leave every first-run artifact on disk, byte-identical.

    Red-before: N/A — no production change in the side-effect surface beyond
    the ``page_refs`` field (and the matching version bump) introduced by this
    PR; this test documents the S5U-662 cache-hit replay invariant for the new
    summary shape. Reviewer asked to cross-check the diff.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites_excluding_extract_layout(ctx)

    assert_cache_hit_replays_artifact(
        ExtractLayoutStage(),
        ctx,
        schema_families={
            "extract_layout",
            "layout_page.v1",
        },
    )

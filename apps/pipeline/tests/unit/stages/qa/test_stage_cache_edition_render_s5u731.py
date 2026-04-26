"""S5U-731 — QAStage version bump invalidates prior-version cached events.

Protects the ``.claude/rules/pipeline.md`` § "Stage-output cache
invalidation" invariant: when ``QAStage._load_render`` and
``QAStage._filter_publishable_pages`` start routing through the
edition-aware helper ``store.edition_selection.load_latest_json_for_edition``
and ``QAStage.version`` is bumped from 1.8 to 1.9, cached events
written under the prior 1.8 cache key must NOT hit — otherwise on a
mixed EN/RU artifact directory the wrong-edition render would still
feed QA's rule evaluation on every cached run.

Scenario:

1. Run prerequisites + seed the QA pipeline so a real page exists.
2. Forge a 'completed' QAStage event under the prior 1.8 cache key
   pointing at a synthetic dead artifact ref.
3. Run ``execute_stage(QAStage(), ctx)``.  Because the live cache key
   uses ``QAStage.version == "1.9"``, the forged 1.8 event is NOT a
   hit, the stage runs, and the live cache key differs from the
   forged one.

If someone reverts the bump to 1.8 the forged event's key matches
the live key; the executor short-circuits with the synthetic dead
artifact ref and the records loader fails because that artifact does
not exist — the failure mode is loud, which is what we want.

Red-before confirmation: commit 7ad85b4 (the branch's parent) has
``QAStage.version == "1.8"``; verified via
``git cat-file -e 7ad85b4^{commit}``. Re-running the pre-fix
QAStage with version 1.8 against the forged 1.8 event would hit
cache (cache_key == prior_key) and the assertion
``qa_result.cache_key != prior_key`` would fail.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.cache_keys import build_cache_key
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
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
        run_id="cache_run_731",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="cache_run_731",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_pipeline(ctx: StageContext) -> None:
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    assert r.artifact_ref is not None
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
        (TranslationStage(), None),
        (RenderStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def _forge_prior_version_event(ctx: StageContext, prior_version: str) -> str:
    """Write a 'completed' QAStage event under a prior version's cache key."""
    qa = QAStage()
    i_hashes: list[str] = []
    if ctx.page_filter:
        i_hashes.append("page_filter:" + "|".join(sorted(ctx.page_filter)))
    prior_key = build_cache_key(
        stage_name=qa.name,
        stage_version=prior_version,
        schema_version="v1",
        config_hash=content_hash(ctx.config.model_dump(mode="json")),
        input_hashes=i_hashes,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name=qa.name,
        scope=qa.scope.value,
        entity_id=ctx.document_id,
        cache_key=prior_key,
    )
    fake_ref = "walking_skeleton/qa/document/walking_skeleton/deadbeef.json"
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=fake_ref,
        duration_ms=0,
    )
    return prior_key


def test_version_bump_invalidates_prior_qa_cache_for_edition_aware_render_load(
    tmp_path: Path,
) -> None:
    """S5U-731 cache-invariance — a prior-version (1.8) cached QA event
    must NOT hit when ``QAStage.version`` is bumped to 1.9 for the
    edition-aware render-load (``_load_render`` and
    ``_filter_publishable_pages``).

    If the bump is reverted (version back to 1.8), the forged 1.8 event's
    cache key matches the live cache key and the assertion
    ``qa_result.cache_key != prior_key`` would fail.
    """
    ctx = _make_ctx(tmp_path)
    _run_pipeline(ctx)

    prior_key = _forge_prior_version_event(ctx, prior_version="1.8")

    qa_result = execute_stage(QAStage(), ctx)
    assert qa_result.success
    assert qa_result.artifact_ref is not None
    assert qa_result.cache_key != prior_key, (
        "QAStage cache key collided with the forged 1.8 event — "
        "version bump did not differentiate the key space."
    )
    assert not qa_result.cached, (
        "QAStage.execute_stage should have missed the 1.8 cached event; "
        "a cache hit here means the version bump is ineffective."
    )

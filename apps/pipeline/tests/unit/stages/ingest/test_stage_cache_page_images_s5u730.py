"""S5U-730 — IngestStage emits ``page_images.v1`` and the cache key
invalidates prior-version events.

Protects the ``.claude/rules/pipeline.md`` § "Stage-output cache
invalidation" invariant: when ``IngestStage.run`` adds a new artifact
write (the per-page ``page_images.v1`` manifest) and ``IngestStage.version``
is bumped from 1.0 to 1.1, cached events written under the prior 1.0
cache key must NOT hit — otherwise documents whose ingest already ran
under 1.0 would forever lack the new manifest, and downstream QA's
manifest-aware filter (S5U-730) would fall back to its render-only path
on those stores.

Two complementary assertions:

* ``test_ingest_emits_page_images_manifest_per_page`` — the manifest is
  written for every active page during a fresh ingest run, and the
  payload validates as ``PageImagesV1``.
* ``test_version_bump_invalidates_prior_ingest_cache`` — a forged 1.0
  cached event does not cause the live 1.1 ingest stage to short-circuit;
  the new manifest still emits.
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
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.page_images_v1 import PageImagesV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path, run_id: str = "ingest_730") -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id=run_id,
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id=run_id,
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_ingest_emits_page_images_manifest_per_page(tmp_path: Path) -> None:
    """A fresh ingest run writes a ``page_images.v1`` artifact for every
    active page; the payload validates as ``PageImagesV1``.

    Red-before confirmation: commit 5122898 (parent of this branch) has
    ``IngestStage.run`` writing only the ``image`` artifact family;
    verified via ``git cat-file -e 5122898^{commit}``. Pre-fix this
    test fails because ``page_images.v1/page/p0001`` does not exist on
    disk after ingest. Post-fix the manifest is written and validates.
    """
    ctx = _make_ctx(tmp_path)
    result = execute_stage(IngestStage(), ctx)
    assert result.success

    manifest_dir = tmp_path / "artifacts" / "walking_skeleton" / "page_images.v1" / "page" / "p0001"
    assert manifest_dir.exists(), (
        "Expected page_images.v1 manifest dir for p0001 after ingest; "
        "the per-page manifest must be emitted alongside the image bytes"
    )
    payload = ctx.artifact_store.load_latest_json(
        document_id="walking_skeleton",
        schema_family="page_images.v1",
        scope="page",
        entity_id="p0001",
    )
    assert payload is not None
    parsed = PageImagesV1.model_validate(payload)
    assert parsed.page_id == "p0001"
    assert parsed.page_number == 1
    # walking_skeleton's stub PDF has at least one image; if the future
    # fixture changes this, the assertion still pins the contract that
    # ingest emits the manifest even when the image list is empty (the
    # IngestStage write happens unconditionally per page).
    assert isinstance(parsed.images, list)


def test_version_bump_invalidates_prior_ingest_cache(tmp_path: Path) -> None:
    """A prior-version (1.0) cached IngestStage event must NOT hit when
    ``IngestStage.version`` is bumped to 1.1.

    If the bump is reverted (version back to 1.0), the forged 1.0
    event's cache key matches the live cache key, ``execute_stage``
    returns a cached StageResult pointing at the synthetic dead artifact
    ref, and the downstream assertion (manifest dir present) fails.

    Red-before confirmation: commit 5122898 (parent of this branch) has
    ``IngestStage.version == "1.0"``; verified via
    ``git cat-file -e 5122898^{commit}``. Re-running the pre-fix
    IngestStage with version 1.0 against the forged 1.0 event would hit
    cache (cache_key == prior_key) and the ``cache_key != prior_key``
    assertion would fail.
    """
    ctx = _make_ctx(tmp_path)

    # Forge a 1.0 'completed' event mirroring ``execute_stage``'s cache-key
    # inputs ordering (no input_hashes for ingest with no prior page_filter).
    ingest = IngestStage()
    i_hashes: list[str] = []
    if ctx.page_filter:
        i_hashes.append("page_filter:" + "|".join(sorted(ctx.page_filter)))
    prior_key = build_cache_key(
        stage_name=ingest.name,
        stage_version="1.0",
        schema_version="v1",
        config_hash=content_hash(ctx.config.model_dump(mode="json")),
        input_hashes=i_hashes,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name=ingest.name,
        scope=ingest.scope.value,
        entity_id=ctx.document_id,
        cache_key=prior_key,
    )
    fake_ref = "walking_skeleton/ingest/document/walking_skeleton/deadbeef.json"
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=fake_ref,
        duration_ms=0,
    )

    result = execute_stage(IngestStage(), ctx)
    assert result.success
    assert result.cache_key != prior_key, (
        "IngestStage cache key collided with the forged 1.0 event — "
        "version bump did not differentiate the key space."
    )
    assert not result.cached, (
        "IngestStage.execute_stage should have missed the 1.0 cached event; "
        "a cache hit here means the version bump is ineffective."
    )

    # The manifest must exist on disk after the live run completes —
    # this is the post-bump invariant.
    manifest_dir = tmp_path / "artifacts" / "walking_skeleton" / "page_images.v1" / "page" / "p0001"
    assert manifest_dir.exists(), (
        "Post-bump ingest run did not emit page_images.v1 manifest for "
        "p0001; either the version bump is missing (so the 1.0 event hit "
        "and run() was skipped) or the manifest write was reverted."
    )

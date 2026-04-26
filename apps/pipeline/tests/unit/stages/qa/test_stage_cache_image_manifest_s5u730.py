"""S5U-730 — QAStage version bump invalidates prior-version cached events.

Protects the ``.claude/rules/pipeline.md`` § "Stage-output cache
invalidation" invariant: when ``QAStage._filter_publishable_pages``
starts reading the new ``page_images.v1`` manifest and ``QAStage.version``
is bumped from 1.7 to 1.8, cached events written under the prior 1.7 cache
key must NOT hit — otherwise pages rescued by image injection would
remain misclassified as dead-page-ref targets on every cached run.

Scenario:

1. Run prerequisites + emit a ``page_images.v1`` manifest claiming an
   exporter-rescuable image on a synthetic ``p0999`` whose render is
   empty.
2. Seed a ``p. 999`` cross-ref on the real page.
3. Forge a 'completed' QAStage event under the prior 1.7 cache key
   pointing at a synthetic dead artifact ref.
4. Run ``execute_stage(QAStage(), ctx)``.  Because the live cache key
   uses ``QAStage.version == "1.8"``, the forged 1.7 event is NOT a
   hit, the stage runs, the manifest-aware filter suppresses the dead
   ref, and the assertion below holds.

If someone reverts the bump to 1.7 the forged event's key matches the
live key; the executor short-circuits with the synthetic dead artifact
ref and the records loader fails because that artifact does not
exist — the failure mode is loud, which is what we want.
"""

from __future__ import annotations

import json
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
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.page_images_v1 import PageImageEntry, PageImagesV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)
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
        run_id="cache_run_730",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="cache_run_730",
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


def _seed_p0999_with_image(ctx: StageContext, real_page_id: str) -> None:
    """Seed an EN/RU IR pair, an empty render, and a ``page_images.v1``
    manifest claiming a 200x200 image for p0999."""
    for family in ("page_ir.v1.en", "page_ir.v1.ru"):
        src = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=family,
            scope="page",
            entity_id=real_page_id,
        )
        assert src is not None
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family=family,
            scope="page",
            entity_id="p0999",
            data=src,
        )
    empty_render = RenderPageV1(
        page=RenderPageMeta(id="p0999", title="Empty", source_page_number=999),
        blocks=[],
        source_map=RenderSourceMap(page_id="p0999", block_refs=[]),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id="p0999",
        data=empty_render,
    )
    manifest = PageImagesV1(
        document_id=ctx.document_id,
        page_id="p0999",
        page_number=999,
        images=[
            PageImageEntry(
                image_id="p0999.img0000",
                width_px=200,
                height_px=200,
                extension=".png",
            )
        ],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_images.v1",
        scope="page",
        entity_id="p0999",
        data=manifest,
    )


def _seed_cross_ref_render(ctx: StageContext, page_id: str) -> None:
    ref_render = RenderPageV1(
        page=RenderPageMeta(id=page_id, title="Test", source_page_number=1),
        blocks=[
            RenderParagraphBlock(
                id="b_crossref",
                children=[RenderTextInline(text="See rules on p. 999 for details")],
            )
        ],
        source_map=RenderSourceMap(page_id=page_id, block_refs=[]),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
        data=ref_render,
    )


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


def _records_for(ctx: StageContext, artifact_ref: ArtifactRef) -> list[QARecordV1]:
    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(artifact_ref))
    out: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = ctx.artifact_store.root / ref
        with open(path, encoding="utf-8") as f:
            out.append(QARecordV1.model_validate(json.load(f)))
    return out


def test_version_bump_invalidates_prior_qa_cache_for_image_manifest(
    tmp_path: Path,
) -> None:
    """S5U-730 cache-invariance — a prior-version (1.7) cached QA event
    must NOT hit when ``QAStage.version`` is bumped to 1.8 for the
    image-manifest publishability filter.

    If the bump is reverted (version back to 1.7), the forged 1.7 event's
    cache key matches the live cache key, ``execute_stage`` returns a
    cached StageResult pointing at the synthetic dead artifact ref, and
    the records loader fails (the artifact does not exist).

    Red-before confirmation: commit 5122898 (parent of this branch)
    has ``QAStage.version == "1.7"``; verified via
    ``git cat-file -e 5122898^{commit}``. Re-running the pre-fix
    QAStage with version 1.7 against the forged 1.7 event would hit
    cache (cache_key == prior_key) and the assertion
    ``qa_result.cache_key != prior_key`` would fail.
    """
    ctx = _make_ctx(tmp_path)
    _run_pipeline(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    _seed_p0999_with_image(ctx, real_page_id)
    _seed_cross_ref_render(ctx, real_page_id)

    prior_key = _forge_prior_version_event(ctx, prior_version="1.7")

    qa_result = execute_stage(QAStage(), ctx)
    assert qa_result.success
    assert qa_result.artifact_ref is not None
    assert qa_result.cache_key != prior_key, (
        "QAStage cache key collided with the forged 1.7 event — "
        "version bump did not differentiate the key space."
    )
    assert not qa_result.cached, (
        "QAStage.execute_stage should have missed the 1.7 cached event; "
        "a cache hit here means the version bump is ineffective."
    )

    records = _records_for(ctx, qa_result.artifact_ref)
    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF" and "p. 999" in r.message]
    assert dead_refs == [], (
        "Post-bump QA run should suppress p. 999 (p0999 has a 200x200 image "
        "in its page_images.v1 manifest, so the exporter would rescue the "
        f"page); got {[r.message for r in dead_refs]}"
    )

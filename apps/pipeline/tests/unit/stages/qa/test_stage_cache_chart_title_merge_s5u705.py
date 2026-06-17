"""S5U-705 — QA stage version bump invalidates prior-version cached events.

Protects the ``.claude/rules/pipeline.md`` § "Stage-output cache
invalidation" invariant for the S5U-705 bump: when
``chart_title_merge_rule`` starts writing the real ``document_id`` into
``QARecordV1.document_id`` (instead of the ``render_page.source_map.page_id``
it used pre-fix), cached QA records from the prior ``QAStage.version``
(``"1.4"``) carry the wrong value — so the version bump to ``"1.5"``
must invalidate those cached events.

Scenario:

1. Run the upstream pipeline to populate EN/RU IR + render artifacts.
2. Seed a render page with a glue-pattern heading that the rule fires
   on.
3. Forge a prior-version (1.5) cached QA event in the registry as if a
   historical run had completed.
4. Run ``execute_stage(QAStage(), ctx)``. Because ``QAStage.version`` is
   now ``"1.6"``, the live cache key differs from the forged 1.5 key —
   the 1.5 event is NOT a hit, the stage runs, and the emitted
   ``CHART_TITLE_MERGE`` record carries the real document id.

If the bump is reverted to the prior version the forged-event key
matches, the executor short-circuits on the synthetic artifact ref,
and the assertions below fail — which is exactly the regression we're
guarding against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderPageMeta,
    RenderPageV1,
    RenderSourceMap,
    RenderTextInline,
)
from atr_schemas.source_manifest_v1 import SourceManifestV1

from ._render_binding_helpers import rebind_run_render

# S5U-1230: full-pipeline-chain integration tests — excluded from the
# fast pre-commit subset via `-m "not slow"`. CI runs the full suite.
pytestmark = pytest.mark.slow


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="cache_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="cache_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_pipeline(ctx: StageContext) -> None:
    r = execute_stage(IngestStage(), ctx)
    assert r.success
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


def _seed_glue_heading_render(ctx: StageContext, page_id: str) -> None:
    render_page = RenderPageV1(
        page=RenderPageMeta(id=page_id, title="Cache regression", source_page_number=1),
        blocks=[
            RenderHeadingBlock(
                id=f"{page_id}.b001",
                level=2,
                # Colon-glue (":B") triggers chart_title_merge_rule.
                children=[RenderTextInline(text="Wounded card:BP deckAI deck")],
            ),
        ],
        source_map=RenderSourceMap(
            document_id="walking_skeleton",
            page_id=page_id,
            block_refs=[],
        ),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
        data=render_page,
    )


def _forge_prior_version_event(
    ctx: StageContext,
    prior_version: str,
) -> str:
    """Write a 'completed' QAStage event to the registry under a prior
    version's cache key.  If ``QAStage.version`` were reverted to this
    prior value, ``execute_stage`` would hit this event and short-circuit.
    """
    qa = QAStage()
    # Replicate execute_stage's cache-key inputs ordering.
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
    # Synthetic artifact ref; the real existence doesn't matter for the
    # cache lookup because the test only asserts that the current-version
    # cache key differs from this forged prior-version key.
    fake_ref = "walking_skeleton/qa/document/walking_skeleton/deadbeef.json"
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=fake_ref,
        duration_ms=0,
    )
    return prior_key


def _records_for(ctx: StageContext, artifact_ref: object) -> list[QARecordV1]:
    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(artifact_ref))  # type: ignore[arg-type]
    out: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = ctx.artifact_store.root / ref  # type: ignore[operator]
        with open(path, encoding="utf-8") as f:
            out.append(QARecordV1.model_validate(json.load(f)))
    return out


def test_version_bump_invalidates_prior_qa_cache_s5u705(tmp_path: Path) -> None:
    """S5U-705 cache-invariance — a prior-version cached QA event must
    NOT hit when ``QAStage.version`` has been bumped for the
    chart_title_merge doc_id fix.

    The forged event's ``prior_version`` is pinned to the immediately-
    preceding ``QAStage.version`` (``"1.5"`` after S5U-735 bumped to
    ``"1.6"``). If the bump is reverted, the forged event's cache key
    matches the live cache key, ``execute_stage`` returns a cached
    StageResult pointing at the synthetic dead artifact ref, and the
    assertions below (``chart_title`` record present with the real
    document id) fail.
    """
    ctx = _make_ctx(tmp_path)
    _run_pipeline(ctx)

    page_id = "p0001"
    _seed_glue_heading_render(ctx, page_id)
    # S5U-1264 — bind the seeded glue-heading render into the run's render index
    # so QA's run-bound selection evaluates it (not the RenderStage original).
    rebind_run_render(ctx, [page_id])
    ctx.page_filter = frozenset({page_id})

    prior_key = _forge_prior_version_event(ctx, prior_version="1.5")

    qa_result = execute_stage(QAStage(), ctx)
    assert qa_result.success
    assert qa_result.artifact_ref is not None
    assert qa_result.cache_key != prior_key, (
        "QAStage cache key collided with the forged 1.4 event — "
        "version bump did not differentiate the key space."
    )
    assert not qa_result.cached, (
        "QAStage.execute_stage should have missed the 1.4 cached event; "
        "a cache hit here means the version bump is ineffective."
    )
    records = _records_for(ctx, qa_result.artifact_ref)
    chart = [r for r in records if r.code == "CHART_TITLE_MERGE"]
    assert len(chart) == 1, (
        "Post-bump QA run did not emit CHART_TITLE_MERGE. Either the "
        "version bump is missing (so the 1.4 event hit), the rule is "
        "not wired in the registry, or the heading pattern drifted. Got "
        f"codes: {[r.code for r in records]}"
    )
    rec = chart[0]
    # The whole point of the bump: the record's document_id is the real
    # parent document id (``"walking_skeleton"``), NOT the page id
    # (``"p0001"``) that the pre-S5U-705 rule emitted.
    assert rec.document_id == "walking_skeleton"
    assert rec.document_id != rec.page_id
    assert rec.entity_ref == f"{page_id}.b001"

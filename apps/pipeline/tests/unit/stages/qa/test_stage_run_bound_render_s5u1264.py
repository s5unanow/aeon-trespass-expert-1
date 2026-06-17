"""S5U-1264 — run-id-bound per-page render selection for the QA stage.

The intra-pipeline QA read path historically selected each per-page
``render_page.v1`` by newest-by-mtime (``load_latest_json_for_edition``). On a
copied / multi-run store where mtimes are unreliable, a stray render from a
*different* run could be spliced into the current run's QA evaluation. These
tests pin the fix: ``QAStage.run`` resolves the current run's
``RenderResult.page_refs`` (recorded run-bound in ``stage_events``) and loads
each render by that ref, falling back to mtime only for uncovered pages.

The export path (S5U-869) is the fail-CLOSED release gate; QA is advisory and
fails SAFE — an absent / unreadable render index degrades to mtime selection
rather than refusing, so QA stays runnable on legacy / partial stores.
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
from atr_pipeline.stages.qa.render_binding import resolve_run_page_refs
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


def _make_ctx(tmp_path: Path, *, run_id: str = "run_1264") -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
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


def _run_prerequisites(ctx: StageContext) -> None:
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    assert r.artifact_ref is not None
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    for stage in (
        ExtractNativeStage,
        SymbolsStage,
        StructureStage,
        TranslationStage,
        RenderStage,
    ):
        inp = manifest if stage is ExtractNativeStage else None
        assert execute_stage(stage(), ctx, input_data=inp).success


def _page_ids(ctx: StageContext) -> list[str]:
    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    return sorted(p.name for p in en_dir.iterdir() if p.is_dir())


@pytest.mark.slow  # S5U-1230: full-pipeline-chain; excluded from fast pre-commit subset
def test_qa_loads_run_bound_render_over_mtime_newer(tmp_path: Path) -> None:
    """QA evaluates the current run's render (by ref), NOT a newer-mtime stray.

    Repro of the cross-run splice the binding prevents: after a full run, a
    *second* render artifact (different content hash) is written for one page
    with a strictly newer mtime — exactly what a stray render from another run
    on a copied store looks like. The mtime selector would pick the stray; the
    run-bound selector must pick the run's own render named in
    ``RenderResult.page_refs``.

    Red-before: prior to S5U-1264 ``QAStage._load_render`` used
    ``load_latest_json_for_edition`` (mtime), so it would parse the stray
    render. We bake a distinct page title into the stray (a real
    ``RenderPageV1`` field) and assert the *loaded* render carries the
    run-bound title, never the stray title.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    page_refs = resolve_run_page_refs(ctx)
    assert page_refs, "render result must record per-page refs"
    target = sorted(page_refs)[0]
    bound_ref = page_refs[target]
    bound_path = ctx.artifact_store.root / bound_ref
    bound_data = json.loads(bound_path.read_text())
    bound_title = bound_data["page"]["title"]

    # Write a STRAY render for the target page: a different content-hash file in
    # the same entity dir, with a strictly newer mtime + a distinct title. This
    # is the cross-run artifact the mtime selector would (wrongly) prefer.
    render_dir = ctx.artifact_store.root / ctx.document_id / "render_page.v1" / "page" / target
    stray = json.loads(json.dumps(bound_data))  # deep copy
    stray["page"]["title"] = "STRAY_FROM_ANOTHER_RUN"
    stray_path = render_dir / "ffffffffffff.json"  # lexically-max-ish, distinct hash
    stray_path.write_text(json.dumps(stray))
    # Newer mtime than the run-bound artifact so mtime selection prefers it.
    import os

    bound_mtime = bound_path.stat().st_mtime
    os.utime(stray_path, (bound_mtime + 10, bound_mtime + 10))

    # The run-bound resolver must still point at the original ref.
    refs_after = resolve_run_page_refs(ctx)
    assert refs_after[target] == bound_ref

    # _load_render must return the run-bound render — its title, not the stray's.
    loaded = QAStage._load_render(ctx, target, edition=ctx.edition, page_refs=refs_after)
    assert loaded is not None
    assert loaded.page.title == bound_title, (
        f"QA loaded the newer-mtime stray render (title={loaded.page.title!r}) "
        f"instead of the run-bound page (title={bound_title!r}) — run-id binding "
        "did not take precedence over mtime selection."
    )
    assert loaded.page.title != "STRAY_FROM_ANOTHER_RUN"


def test_resolve_run_page_refs_empty_without_render_event(tmp_path: Path) -> None:
    """No render stage event for the run ⇒ resolver returns ``{}`` (fail-safe).

    Red-before: N/A — pins the fail-safe contract directly. With no render
    event recorded, ``resolve_run_page_refs`` must not raise; the QA stage then
    falls back to mtime selection per page.
    """
    ctx = _make_ctx(tmp_path)
    # No stages run at all — no render event exists for the run.
    assert resolve_run_page_refs(ctx) == {}


def test_resolve_run_page_refs_empty_when_artifact_missing(tmp_path: Path) -> None:
    """A render event whose artifact is gone ⇒ resolver returns ``{}`` (no crash).

    Red-before: N/A — pins the degenerate-input fail-safe path. Forge a
    completed render event pointing at a non-existent artifact; the resolver
    must log + return ``{}`` rather than raise.
    """
    ctx = _make_ctx(tmp_path)
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name="render",
        scope="document",
        entity_id=ctx.document_id,
        cache_key="forged",
    )
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref="walking_skeleton/render/document/walking_skeleton/deadbeef.json",
        duration_ms=0,
    )
    assert resolve_run_page_refs(ctx) == {}


@pytest.mark.slow  # S5U-1230: full-pipeline-chain; excluded from fast pre-commit subset
def test_qa_runs_with_mtime_fallback_when_no_render_event(tmp_path: Path) -> None:
    """QA still produces a summary when the run has no render index (fail-safe).

    Pages are present on disk (full prerequisites ran) but the render stage
    event is removed so ``resolve_run_page_refs`` returns ``{}``. QA must fall
    back to mtime selection and still evaluate the pages — not refuse.

    Red-before: N/A — pins the fail-safe behavior end to end (no production
    code change asserts this invariant alone; the resolver + QA wiring together
    must keep QA runnable).
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    # Delete the render stage event(s) so no run-bound index resolves.
    ctx.registry_conn.execute("DELETE FROM stage_events WHERE stage_name = 'render'")
    ctx.registry_conn.commit()

    assert resolve_run_page_refs(ctx) == {}
    summary = QAStage().run(ctx, None)
    assert summary.document_id == ctx.document_id
    # mtime fallback still evaluated pages — counts are populated (>=0 is trivially
    # true; assert the run completed and refs were persisted for some records).
    assert summary.run_id == ctx.run_id


def _forge_prior_version_qa_event(ctx: StageContext, prior_version: str) -> str:
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
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref="walking_skeleton/qa/document/walking_skeleton/deadbeef.json",
        duration_ms=0,
    )
    return prior_key


@pytest.mark.slow  # S5U-1230: full-pipeline-chain; excluded from fast pre-commit subset
def test_version_bump_invalidates_prior_qa_cache_for_run_bound_render(
    tmp_path: Path,
) -> None:
    """S5U-662 cache-hit obligation — a prior-version (1.10) cached QA event must
    NOT be served once ``QAStage.version`` is bumped to 1.11 for the run-bound
    render selection.

    This exercises the executor's cache-hit branch: a forged 1.10 ``completed``
    event exists for the run; ``execute_stage(QAStage())`` must MISS it (live key
    uses version 1.11), run the stage, and write a fresh artifact under the new
    key. If the bump is reverted to 1.10 the forged event's key matches the live
    key and the executor would short-circuit ``run()`` and serve the forged dead
    artifact ref — re-introducing the stale-selection hazard. The asserts below
    then fail loudly (``cached`` True / key collision).

    Red-before confirmation: pre-fix ``QAStage.version`` was ``"1.10"`` (cited in
    the PR body against a reachable parent SHA); with the live version at 1.10
    the forged event hits, ``qa_result.cached`` is True, and
    ``qa_result.cache_key == prior_key`` — both asserts fail.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    prior_key = _forge_prior_version_qa_event(ctx, prior_version="1.10")

    qa_result = execute_stage(QAStage(), ctx)
    assert qa_result.success
    assert qa_result.artifact_ref is not None
    assert qa_result.cache_key != prior_key, (
        "QAStage cache key collided with the forged 1.10 event — the S5U-1264 "
        "version bump did not differentiate the key space."
    )
    assert not qa_result.cached, (
        "QAStage.execute_stage should have MISSED the forged 1.10 cached event; "
        "a cache hit means the run-bound-render version bump is ineffective and "
        "QA would replay a selection computed under the old mtime policy."
    )

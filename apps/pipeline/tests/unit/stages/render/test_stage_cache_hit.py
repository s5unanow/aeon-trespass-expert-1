"""S5U-740 — RenderStage cache-hit replay regression (pipeline.md § "Stage-output
cache invalidation", clause 2).

S5U-581 bumped ``RenderStage.version`` 1.4 → 1.5: ``CalloutBlock`` now emits
a ``RenderCalloutBlock`` instead of being silently dropped, so the
``render_page.v1`` artifact shape changes for any callout-bearing page.
``.claude/rules/pipeline.md`` line 15 (S5U-662) requires *both* the version
bump *and* a regression test that exercises the executor's cache-hit path
and asserts the new side-effect/behavior is preserved on cached runs. The
version bump landed in PR #334, but the paired cache-hit test did not —
this file closes that second-half gap.

## What the test guards against

The executor's cache-hit branch (``runner/executor.py:56-83``) short-circuits
``stage.run()`` — it returns a cached ``StageResult`` pointing at the
previously persisted artifact ref and never re-executes the stage's
``run()`` body. If a future PR adds a new ``ctx.artifact_store.put_json(...)``
/ ``put_binary(...)`` / ``atomic_write_*`` call to ``RenderStage.run()``
**without** bumping the ``version`` field, subsequent runs on the same
cache key will skip that write entirely — and the new artifact will be
silently absent for every pre-existing run and every future cache hit.

The exact S5U-597 → S5U-640 retrospective is the concrete precedent the
rule was created to prevent (``qa_metrics.json`` was added to
``QAStage.run`` in S5U-597 with ``version`` unchanged, so cached runs
silently omitted the artifact until S5U-640 bumped the version). This
test makes the rule mechanical for ``RenderStage``.

## Shape of the tests

Both tests below use the executor cache-hit invariant helper
(``assert_cache_hit_replays_artifact``) from
``tests/unit/stages/qa/test_stage_cache_hit.py``. The helper runs the
stage twice via ``execute_stage(stage, ctx)``:

1. First call: miss — ``run()`` executes, artifacts are persisted.
2. Second call: hit — ``run()`` short-circuits, the cached ref is
   returned, and every artifact that existed after run 1 is asserted
   present and byte-identical after run 2.

``test_render_stage_cache_hit_preserves_callout_output`` is the
S5U-581-specific test: the prepared context contains a ``CalloutBlock``
in the page IR, so the persisted ``render_page.v1`` artifact carries a
``RenderCalloutBlock`` (the post-S5U-581 shape). The test asserts that
shape survives the cache hit — which is exactly the invariant
``.claude/rules/pipeline.md`` clause 2 requires for the 1.4 → 1.5 bump.

``test_render_stage_cache_hit_preserves_render_output`` is the generic
companion: any future ``RenderStage`` version bump (or any new persisted
side-effect inside ``RenderStage.run()``) must keep this test green.
It guards the same invariant for every ``render_page.v1`` artifact plus
the companion families ``glossary_payload.v1``, ``search_docs.v1``, and
``nav.v1`` that ``run()`` emits.

If a future PR adds a new ``put_json`` / ``put_binary`` /
``atomic_write_*`` call to ``RenderStage.run()`` without bumping
``RenderStage.version``, extend the ``schema_families`` set on the
generic test below to include the new family. The helper will then
guard it against the same silent-omission class.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.render.stage import RenderResult, RenderStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    PageIRV1,
    ParagraphBlock,
    TermMarkInline,
    TextInline,
)
from atr_schemas.render_page_v1 import RenderPageV1
from tests.unit.stages.qa.test_stage_cache_hit import (
    assert_cache_hit_replays_artifact,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _published_render_page(page_dir: Path) -> RenderPageV1:
    """Return the wrapper that carries the immutable review target ref."""
    page_files = list(page_dir.glob("*.json"))
    assert len(page_files) == 2, f"expected target + published render pages, got {page_files}"
    pages = [RenderPageV1.model_validate_json(path.read_bytes()) for path in page_files]
    published = [page for page in pages if page.build_meta and page.build_meta.artifact_ref]
    assert len(published) == 1, f"expected one published wrapper, got {published}"
    wrapper = published[0]
    assert wrapper.build_meta is not None
    assert (page_dir / Path(wrapper.build_meta.artifact_ref).name).exists()
    return wrapper


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="render_cache_hit_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="render_cache_hit_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _put_callout_page_ir(ctx: StageContext, *, page_id: str = "p0001") -> None:
    """Inject an EN page IR carrying a CalloutBlock into the artifact store.

    RenderStage reads page IR directly from the store via
    ``_resolve_page_ids`` + ``_load_page_ir``, so we can prepare a
    callout-bearing fixture without running ingest/extract/structure/
    translate. The post-S5U-581 ``page_builder`` emits a
    ``RenderCalloutBlock`` for this IR; the cache-hit invariant must
    preserve the persisted ``render_page.v1`` carrying that block.
    """
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id=page_id,
        page_number=int(page_id.removeprefix("p")),
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id=f"{page_id}.b001",
                children=[TextInline(text="Body paragraph.", lang=LanguageCode.EN)],
            ),
            CalloutBlock(
                block_id=f"{page_id}.b002",
                variant="info",
                children=[TextInline(text="Callout body.", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=[f"{page_id}.b001", f"{page_id}.b002"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
        data=ir,
    )


def test_render_stage_cache_hit_preserves_callout_output(tmp_path: Path) -> None:
    """S5U-740 — the S5U-581 cache-invalidation behavior must replay across cache hits.

    Run RenderStage twice on a context whose IR carries a CalloutBlock:

    1. First run is a miss — ``run()`` executes ``build_render_page`` which
       (post-S5U-581) emits a ``RenderCalloutBlock`` into the persisted
       ``render_page.v1`` artifact for ``p0001``.
    2. Second run is a hit — the executor short-circuits ``run()`` and
       returns the cached ref.

    After the hit, the ``render_page.v1/page/p0001`` artifact must still
    be on disk byte-identical to the first run, and (defensive cross-
    check) it must carry a ``RenderCalloutBlock`` — i.e. the S5U-581
    behavior the 1.4 → 1.5 bump exists to invalidate-and-replay.

    Live-regression ergonomics: the test exercises the exact invariant
    pipeline.md clause 2 names — if ``RenderStage.version`` regressed to
    a value that pre-dates the callout dispatch (e.g. ``"1.4"``), the
    second-run cache-hit assertion in
    ``assert_cache_hit_replays_artifact`` would still pass for *this*
    test alone (the bytes don't change just because the version label
    does), but the version-pin assertion in
    ``test_render_implements_stage_protocol`` (test_stage.py:84) would
    fail first — the two tests together close the loop. See the
    "Live-regression confirmation" line in the S5U-740 commit message
    for the locally observed failure shape.
    """
    ctx = _make_ctx(tmp_path)
    _put_callout_page_ir(ctx, page_id="p0001")

    assert_cache_hit_replays_artifact(
        RenderStage(),
        ctx,
        schema_families={
            "render",
            "render_page.v1",
            "glossary_payload.v1",
            "search_docs.v1",
            "nav.v1",
        },
    )

    # Cross-check: the persisted render page for the callout-bearing
    # input actually carries the RenderCalloutBlock. This is the
    # S5U-581 behavior the 1.4 → 1.5 cache-invalidation rule exists to
    # replay. If a future regression silently drops callout dispatch
    # again, this assertion fails before the cache-hit invariant does.
    page_dir = tmp_path / "artifacts" / "walking_skeleton" / "render_page.v1" / "page" / "p0001"
    render_page = _published_render_page(page_dir)
    callout_blocks = [b for b in render_page.blocks if b.kind == "callout"]
    assert len(callout_blocks) == 1, (
        "expected exactly one RenderCalloutBlock in the persisted render page; "
        f"got blocks={[b.kind for b in render_page.blocks]} — has the S5U-581 "
        "callout dispatch in build_render_page regressed?"
    )


def test_render_stage_cache_hit_preserves_render_output(tmp_path: Path) -> None:
    """S5U-740 — generic ``RenderStage`` cache-hit replay invariant.

    Companion to ``test_render_stage_cache_hit_preserves_callout_output``.
    This test does not depend on the S5U-581 callout dispatch — it pins
    the cache-hit invariant on a callout-free page so that future
    ``RenderStage`` version bumps (or new persisted side-effects in
    ``RenderStage.run()``) keep the rule mechanical regardless of which
    block types the new behavior touches.

    Guarded schema families:

    * ``render`` — the executor-written summary artifact (``RenderResult``).
    * ``render_page.v1`` — the per-page render artifact emitted from
      inside ``RenderStage.run()``.
    * ``glossary_payload.v1`` / ``search_docs.v1`` / ``nav.v1`` —
      companion artifacts emitted by ``_emit_companion_artifacts`` from
      inside ``RenderStage.run()``. These are exactly the S5U-597-class
      side-effects pipeline.md clause 2 was created to protect.

    If ``RenderStage.run()`` gains a new persisted family in a future
    PR, extend the set below.
    """
    ctx = _make_ctx(tmp_path)
    # Callout-free page: a single paragraph. Exercises the executor
    # cache-hit branch without depending on the S5U-581 dispatch.
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="Hello world.", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=ir,
    )

    assert_cache_hit_replays_artifact(
        RenderStage(),
        ctx,
        schema_families={
            "render",
            "render_page.v1",
            "glossary_payload.v1",
            "search_docs.v1",
            "nav.v1",
        },
    )

    # Sanity: the executor-written ``render`` summary parses as RenderResult
    # and points at the per-page artifact. If a future refactor changes
    # the executor's summary schema_family for RenderStage, this catches
    # it before the cache-hit assertion does.
    render_dir = tmp_path / "artifacts" / "walking_skeleton" / "render"
    summaries = list(render_dir.rglob("*.json"))
    assert summaries, "expected RenderStage executor summary artifact"
    RenderResult.model_validate_json(summaries[0].read_bytes())


def test_render_stage_cache_hit_preserves_term_mark_dispatch(tmp_path: Path) -> None:
    """S5U-745 — the term_mark dispatch behavior must replay across cache hits.

    Run RenderStage twice on a context whose IR carries a
    ``TermMarkInline``:

    1. First run is a miss — ``run()`` executes ``build_render_page``
       which (post-S5U-745) flattens the term_mark to a
       ``RenderTextInline(text=surface_form)`` in the persisted
       ``render_page.v1`` artifact for ``p0001``.
    2. Second run is a hit — the executor short-circuits ``run()`` and
       returns the cached ref.

    After the hit, the ``render_page.v1/page/p0001`` artifact must still
    be on disk byte-identical to the first run, and (defensive cross-
    check) it must carry the flattened ``RenderTextInline`` whose text
    is the IR node's surface_form — i.e. the S5U-745 dispatch behavior
    that replaces the silent drop.

    Live-regression ergonomics: this test does not require a
    ``RenderStage.version`` bump (Decision 4 in tmp/plan-s5u-745.md
    explains why no real cached corpus is affected today). What it
    does guard is the per-page-bytes contract — if a future refactor
    silently regresses the term_mark dispatch (e.g. by reordering the
    isinstance chain in a way that drops the new branch), the second
    pass of the cache-hit invariant would still pass byte-for-byte
    against the regression's own broken first run, but the
    ``len(text_blocks) >= 1`` cross-check below fails before the
    silent drop reaches main.
    """
    ctx = _make_ctx(tmp_path)
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="see ", lang=LanguageCode.EN),
                    TermMarkInline(concept_id="concept.cypher", surface_form="cypher"),
                ],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=ir,
    )

    assert_cache_hit_replays_artifact(
        RenderStage(),
        ctx,
        schema_families={
            "render",
            "render_page.v1",
            "glossary_payload.v1",
            "search_docs.v1",
            "nav.v1",
        },
    )

    # Cross-check: the persisted render page for the term_mark-bearing
    # input actually carries the flattened RenderTextInline. This is
    # the S5U-745 dispatch behavior that replaces the silent drop; if
    # a future regression silently drops term_mark dispatch again, this
    # assertion fails before the cache-hit invariant does.
    page_dir = tmp_path / "artifacts" / "walking_skeleton" / "render_page.v1" / "page" / "p0001"
    render_page = _published_render_page(page_dir)
    para_blocks = [b for b in render_page.blocks if b.kind == "paragraph"]
    assert len(para_blocks) == 1, (
        f"expected one paragraph; got {[b.kind for b in render_page.blocks]}"
    )
    para = para_blocks[0]
    text_kinds = [c.kind for c in para.children]
    assert text_kinds == ["text", "text"], (
        f"expected ['text', 'text'] (TextInline + flattened TermMarkInline); "
        f"got {text_kinds} — has the S5U-745 term_mark dispatch in "
        "build_render_page regressed?"
    )
    text_values = [c.text for c in para.children]  # type: ignore[union-attr]
    assert text_values == ["see ", "cypher"], (
        f"expected text values ['see ', 'cypher']; got {text_values}"
    )

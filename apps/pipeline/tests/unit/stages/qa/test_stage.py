"""Tests for the QA stage."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.qa.user_feedback import persist_submissions
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.common import ConfidenceMetrics
from atr_schemas.enums import QALayer, StageScope
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_metrics_v1 import QAMetricsV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.review_pack_v1 import ReviewPackV1
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
    """Run ingest → extract_native → symbols → structure → translate → render."""
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


def test_qa_implements_stage_protocol() -> None:
    """QAStage satisfies the Stage protocol."""
    stage = QAStage()
    assert isinstance(stage, Stage)
    assert stage.name == "qa"
    assert stage.scope == StageScope.DOCUMENT
    # 1.2 → 1.3 in S5U-701: manifest-aware DEAD_PAGE_REF + new
    # PLACEHOLDER_PROSE_LEAKED (ERROR) record are new observable
    # side effects — version bump invalidates pre-S5U-701 cached QA
    # events so false-positive records are suppressed and new ones emit.
    assert stage.version == "1.3"


def test_qa_persists_summary_clean_pipeline(tmp_path: Path) -> None:
    """QAStage persists a QASummaryV1 with no blocking issues."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    summary = QASummaryV1.model_validate(data)
    assert summary.document_id == "walking_skeleton"
    assert summary.run_id == "test_run"
    assert summary.blocking is False
    assert summary.counts.error == 0
    assert summary.counts.critical == 0
    assert summary.record_refs == []


def test_qa_persists_qa_metrics_artifact(tmp_path: Path) -> None:
    """S5U-597: QA stage writes a QAMetricsV1 artifact alongside the summary.

    The metrics file must live at ``<doc>/qa_metrics.v1/document/<doc>/`` with
    ``pages_total`` matching the EN IR page count, and must validate against
    the ``QAMetricsV1`` model.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(QAStage(), ctx)
    assert result.success

    metrics_dir = (
        ctx.artifact_store.root / ctx.document_id / "qa_metrics.v1" / "document" / ctx.document_id
    )
    assert metrics_dir.is_dir(), "qa_metrics.v1 artifact dir missing"
    files = list(metrics_dir.glob("*.json"))
    assert len(files) == 1

    import json

    metrics = QAMetricsV1.model_validate(json.loads(files[0].read_text()))
    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    expected_pages = sum(1 for p in en_dir.iterdir() if p.is_dir())
    assert metrics.pages_total == expected_pages
    assert metrics.document_id == ctx.document_id
    assert metrics.run_id == ctx.run_id
    assert metrics.schema_version == "qa_metrics.v1"
    # clean pipeline — no blocking findings expected
    assert metrics.blocking_count == 0


def test_qa_raises_without_en_ir(tmp_path: Path) -> None:
    """QAStage fails when no EN IR pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(QAStage(), ctx)
    assert not result.success
    assert "No EN IR pages found" in (result.error or "")


def test_qa_picks_up_user_feedback_for_current_edition(tmp_path: Path) -> None:
    """Ingested user feedback surfaces through QASummaryV1 + record_refs.

    Regression for S5U-605: previously feedback was persisted to a flat
    directory the QA stage never read. This asserts the full loop-closure:
    ingest → ArtifactStore → QA stage → summary/records/review-pack.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    # Discover a page the pipeline actually produced so the feedback is
    # attached to a real page. QAStage filters to pages with EN IR.
    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    submissions = [
        (
            FeedbackSubmissionV1.model_validate(
                {
                    "document_id": ctx.document_id,
                    "edition": ctx.edition if ctx.edition in ("en", "ru") else "ru",
                    "page_id": page_id,
                    "issue_type": "translation",
                    "note": "wrong term",
                    "url": "",
                    "user_agent": "",
                    "timestamp": "2026-04-18T12:34:56.000Z",
                }
            ),
            "sample.json",
        ),
    ]
    persist_submissions(store=ctx.artifact_store, submissions=submissions)

    # The QA stage's default edition is "all"; use the same edition we
    # submitted against so the loader finds it.
    ctx.edition = submissions[0][0].edition

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    # user_feedback is info-level and therefore non-blocking.
    assert summary.blocking is False

    # Resolve the referenced QARecord files off disk (ArtifactStore uses
    # ``relative_path`` refs rooted at the store root).
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        record_path = ctx.artifact_store.root / ref
        records.append(QARecordV1.model_validate(_load_json(record_path)))
    user_feedback_records = [r for r in records if r.layer == QALayer.USER_FEEDBACK]
    assert len(user_feedback_records) == 1
    rec = user_feedback_records[0]
    assert rec.page_id == page_id
    assert rec.code == "USER_FEEDBACK_TRANSLATION"
    assert summary.counts.info >= 1


def test_qa_all_edition_run_loads_both_feedback_editions(tmp_path: Path) -> None:
    """``edition="all"`` must merge EN + RU feedback into the same run.

    Guards against a regression where the loader silently looked up a
    ``user_feedback_record_set.v1.all`` artifact that ingest never writes.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    submissions = [
        (
            FeedbackSubmissionV1.model_validate(
                {
                    "document_id": ctx.document_id,
                    "edition": "ru",
                    "page_id": page_id,
                    "issue_type": "translation",
                    "note": "ru",
                    "url": "",
                    "user_agent": "",
                    "timestamp": "2026-04-18T12:34:56.000Z",
                }
            ),
            "ru.json",
        ),
        (
            FeedbackSubmissionV1.model_validate(
                {
                    "document_id": ctx.document_id,
                    "edition": "en",
                    "page_id": page_id,
                    "issue_type": "extraction",
                    "note": "en",
                    "url": "",
                    "user_agent": "",
                    "timestamp": "2026-04-18T13:00:00.000Z",
                }
            ),
            "en.json",
        ),
    ]
    persist_submissions(store=ctx.artifact_store, submissions=submissions)
    # Default edition in StageContext is "all".
    assert ctx.edition == "all"

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        record_path = ctx.artifact_store.root / ref
        records.append(QARecordV1.model_validate(_load_json(record_path)))
    user_feedback_records = [r for r in records if r.layer == QALayer.USER_FEEDBACK]
    codes = {r.code for r in user_feedback_records}
    assert codes == {"USER_FEEDBACK_TRANSLATION", "USER_FEEDBACK_EXTRACTION"}


def _set_en_confidence(ctx: StageContext, page_id: str, confidence: float) -> None:
    """Overwrite the EN IR for *page_id* with a forced page_confidence."""
    data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
    )
    assert data is not None
    ir = PageIRV1.model_validate(data)
    ir.confidence = ConfidenceMetrics(
        native_text_coverage=confidence,
        reading_order_score=confidence,
        symbol_score=confidence,
        page_confidence=confidence,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
        data=ir,
    )


def _load_review_pack(ctx: StageContext, ref: str) -> ReviewPackV1:
    path = ctx.artifact_store.root / ref
    return ReviewPackV1.model_validate_json(path.read_text(encoding="utf-8"))


def _first_en_page_id(ctx: StageContext) -> str:
    ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())[0]


def test_qa_publish_blocking_band_blocks_release(tmp_path: Path) -> None:
    """A publish_blocking band forces blocking=True and writes a review pack
    containing a CRITICAL confidence record (S5U-588)."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    page_id = _first_en_page_id(ctx)
    _set_en_confidence(ctx, page_id, 0.10)

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    assert summary.blocking is True
    assert summary.counts.critical >= 1
    assert summary.review_pack_ref != ""

    pack = _load_review_pack(ctx, summary.review_pack_ref)
    codes = [f.record.code for f in pack.findings]
    assert "CONFIDENCE_PUBLISH_BLOCKING" in codes


def test_qa_required_band_surfaces_without_blocking(tmp_path: Path) -> None:
    """A qa_required band adds a WARNING review-pack finding without blocking
    release (S5U-588)."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    page_id = _first_en_page_id(ctx)
    _set_en_confidence(ctx, page_id, 0.45)

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    assert summary.blocking is False
    assert summary.counts.warning >= 1
    assert summary.review_pack_ref != ""

    pack = _load_review_pack(ctx, summary.review_pack_ref)
    codes = [f.record.code for f in pack.findings]
    assert "CONFIDENCE_QA_REQUIRED" in codes
    assert pack.blocking_findings == 0


def test_qa_manifest_respects_full_page_set_under_page_filter(tmp_path: Path) -> None:
    """S5U-701 follow-up (Codex REVISE):

    The dead-page-ref rule's manifest-aware suppression set must be derived
    from the FULL published page manifest, not the ``--pages`` selection.

    Pre-fix: ``QAStage.run`` built ``known_page_numbers`` from
    ``ctx.filter_pages(...)``, so a partial QA run would flag every reference
    to an unselected-but-published page as ``DEAD_PAGE_REF``.  This test
    seeds a second published page (``p0999``) into the EN IR / render /
    RU IR artifact stores, puts a ``p. 999`` reference on ``p0001``'s
    render output, then runs QA with ``page_filter = {"p0001"}``.  The fix
    computes ``known_page_numbers`` from ``_resolve_page_ids(ctx)`` before
    filtering; with the fix, no ``DEAD_PAGE_REF`` record fires.  Without the
    fix, the filtered page set omits ``p0999`` and the rule flags ``p. 999``
    as dead — which this assertion catches.

    Red-before confirmation: commit f711b9d shows the pre-S5U-701 rule
    signature without ``known_page_numbers``; verified via
    ``git cat-file -e f711b9d^{commit}``.  Re-running the PRE-FIX build of
    ``QAStage.run`` (``known_page_numbers = _page_ids_to_numbers(page_ids)``
    after ``page_ids = ctx.filter_pages(...)``) against this test emits a
    ``DEAD_PAGE_REF`` for the filtered-away p0999 reference.
    """
    from atr_schemas.render_page_v1 import (
        RenderPageMeta,
        RenderPageV1,
        RenderParagraphBlock,
        RenderSourceMap,
        RenderTextInline,
    )

    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    # Discover the first real page produced by the walking_skeleton pipeline.
    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    # Clone the real EN IR, RU IR, and render artifacts for a synthetic
    # ``p0999`` so the manifest resolver sees two published pages.
    for family in ("page_ir.v1.en", "page_ir.v1.ru", "render_page.v1"):
        src = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=family,
            scope="page",
            entity_id=real_page_id,
        )
        assert src is not None, f"expected {family} seeded by prerequisites"
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family=family,
            scope="page",
            entity_id="p0999",
            data=src,
        )

    # Overwrite ``real_page_id``'s render to include a "p. 999" reference.
    # If the QA stage builds the manifest from the filtered page set, this
    # reference will be flagged as DEAD_PAGE_REF; with the fix, p0999 is in
    # the manifest and the finding is suppressed.
    render_page = RenderPageV1(
        page=RenderPageMeta(id=real_page_id, title="Test", source_page_number=1),
        blocks=[
            RenderParagraphBlock(
                id="b_crossref",
                children=[RenderTextInline(text="See rules on p. 999 for details")],
            )
        ],
        source_map=RenderSourceMap(page_id=real_page_id, block_refs=[]),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=real_page_id,
        data=render_page,
    )

    # Filter QA to just the real page; p0999 stays in the manifest but out
    # of the iterator.
    ctx.page_filter = frozenset({real_page_id})

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        records.append(QARecordV1.model_validate(_load_json(ctx.artifact_store.root / ref)))

    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF"]
    assert dead_refs == [], (
        f"Expected no DEAD_PAGE_REF on p. 999 when p0999 is in the full manifest "
        f"(page_filter={set(ctx.page_filter)}); got {[r.message for r in dead_refs]}"
    )


def test_qa_manifest_excludes_empty_non_facsimile_pages(tmp_path: Path) -> None:
    """S5U-701 follow-up (Codex REVISE round 2):

    The dead-page-ref suppression manifest must match the **web reader's**
    published page set, not the full EN IR directory.  The exporter in
    ``scripts/export_to_web.py::export_pages`` drops non-facsimile pages
    whose render has no blocks (see Lines 221-248 of that file); if QA
    built its manifest from every EN IR page, a reference to such a
    dropped page would pass QA while still being dead for readers.

    This test seeds a synthetic ``p0999`` with an EN/RU IR and a
    non-facsimile render carrying zero blocks.  A paragraph on the real
    page references ``p. 999``.  With the reader-manifest-aligned fix,
    ``p0999`` is NOT in ``known_page_numbers`` (no renderable blocks →
    exporter would drop it), so the reference fires as ``DEAD_PAGE_REF``.

    Red-before confirmation: pre-fix (``known_page_numbers`` built from
    ``_resolve_page_ids(ctx)`` directly without the publishability
    filter) the EN IR presence alone suppressed the finding — the
    assertion ``len(dead_refs) == 1`` would fail with ``[] == 1``.
    Verified by reverting ``_filter_publishable_pages`` locally and
    re-running this test.
    """
    from atr_schemas.render_page_v1 import (
        RenderPageMeta,
        RenderPageV1,
        RenderParagraphBlock,
        RenderSourceMap,
        RenderTextInline,
    )

    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    # Clone EN/RU IR for p0999 (so _resolve_page_ids sees the page),
    # but install an EMPTY non-facsimile render.  This matches the
    # exporter's "would-be-dropped" case.
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

    # Overwrite the real page's render to reference p. 999.
    ref_render = RenderPageV1(
        page=RenderPageMeta(id=real_page_id, title="Test", source_page_number=1),
        blocks=[
            RenderParagraphBlock(
                id="b_crossref",
                children=[RenderTextInline(text="See rules on p. 999 for details")],
            )
        ],
        source_map=RenderSourceMap(page_id=real_page_id, block_refs=[]),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=real_page_id,
        data=ref_render,
    )

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        records.append(QARecordV1.model_validate(_load_json(ctx.artifact_store.root / ref)))

    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF" and "p. 999" in r.message]
    assert len(dead_refs) == 1, (
        "Expected DEAD_PAGE_REF for p. 999 when p0999's render is empty "
        "(exporter would drop it from the reader manifest); "
        f"got {[r.message for r in dead_refs]}"
    )


def _load_json(path: Path) -> dict[str, object]:
    import json

    data: dict[str, object] = json.loads(path.read_text())
    return data

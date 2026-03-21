"""S5U-286: Source-edition end-to-end extraction verification for curated pages.

Validates that golden EN page IRs produce correct render output, pass QA
in source-only mode, and generate valid publish bundles when processed
through the render → QA → publish pipeline path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig, QAConfig
from atr_pipeline.eval.config_loader import load_golden_set
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.publish.stage import PublishStage
from atr_pipeline.stages.qa.registry import QAPageContext
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderResult, RenderStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.render_page_v1 import (
    RenderFigureBlock,
    RenderIconInline,
    RenderPageV1,
)
from atr_schemas.waiver_v1 import WaiverSetV1, WaiverV1

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "packages" / "fixtures" / "sample_documents"

# Curated fixtures — at least 3 required by acceptance criteria.
CURATED_FIXTURES = ["multi_column", "icon_dense", "table_callout", "figure_caption", "hard_route"]

# Only heading, paragraph, list_item, figure types produce render blocks;
# table, callout, caption fall through the page builder without rendering.
_RENDERABLE = {"heading", "paragraph", "list_item", "figure"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    tmp_path: Path,
    doc_id: str,
    *,
    edition: str = "en",
    qa_config: QAConfig | None = None,
) -> StageContext:
    config = DocumentBuildConfig(
        document=DocumentConfig(id=doc_id, source_pdf="dummy.pdf", structure_builder="simple"),
        repo_root=REPO_ROOT,
    )
    updates: dict[str, object] = {"artifact_root": tmp_path / "artifacts"}
    if qa_config is not None:
        updates["qa"] = qa_config
    config = config.model_copy(update=updates)
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="e2e_run",
        document_id=doc_id,
        pipeline_version="0.1.0",
        config_hash="e2e_test",
        edition=edition,
    )
    return StageContext(
        run_id="e2e_run",
        document_id=doc_id,
        config=config,
        artifact_store=store,
        registry_conn=conn,
        edition=edition,
    )


def _seed_golden_irs(store: ArtifactStore, doc_id: str) -> None:
    """Write golden EN page IRs into the artifact store."""
    for ir_file in sorted((FIXTURES / doc_id / "expected").glob("page_ir.en.*.json")):
        page_id = ir_file.stem.removeprefix("page_ir.en.")
        ir = PageIRV1.model_validate(json.loads(ir_file.read_text()))
        store.put_json(
            document_id=doc_id,
            schema_family="page_ir.v1.en",
            scope="page",
            entity_id=page_id,
            data=ir,
        )


def _register_render_event(ctx: StageContext, render_result: RenderResult) -> None:
    """Register a render stage event so publish can find render output."""
    ref = ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="stage_result.render",
        scope="document",
        entity_id=ctx.document_id,
        data=render_result,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name="render",
        scope="document",
        entity_id=ctx.document_id,
        cache_key="e2e_render",
    )
    record_stage_finish(
        ctx.registry_conn, event_id=event_id, status="completed", artifact_ref=ref.relative_path
    )


def _read_render_page(store: ArtifactStore, doc_id: str, page_id: str) -> RenderPageV1:
    page_dir = store.root / doc_id / "render_page.v1" / "page" / page_id
    jsons = sorted(page_dir.glob("*.json"))
    assert jsons, f"No render page artifact for {doc_id}/{page_id}"
    return RenderPageV1.model_validate(json.loads(jsons[-1].read_text()))


def _count_icons(render_page: RenderPageV1) -> int:
    total = 0
    for block in render_page.blocks:
        if not hasattr(block, "children"):
            continue
        for child in block.children:
            if isinstance(child, RenderIconInline):
                total += 1
    return total


def _write_source_only_waivers(tmp_path: Path, doc_id: str) -> Path:
    """Create UNTRANSLATED_TEXT waiver for source-only mode (EN target = EN source)."""
    waivers_dir = tmp_path / "waivers"
    waivers_dir.mkdir(exist_ok=True)
    ws = WaiverSetV1(
        document_id=doc_id,
        waivers=[
            WaiverV1(
                waiver_id="source_only_untranslated",
                code="UNTRANSLATED_TEXT",
                reason="Expected in source-only mode — no translation performed",
                approved_by="e2e_test_harness",
            )
        ],
    )
    (waivers_dir / f"{doc_id}.json").write_text(ws.model_dump_json())
    return waivers_dir


# ---------------------------------------------------------------------------
# Parametrized E2E fixture — runs render + QA per golden document
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class E2EResult:
    doc_id: str
    render_result: RenderResult
    qa_summary: QASummaryV1
    ctx: StageContext


@pytest.fixture(params=CURATED_FIXTURES)
def e2e_run(request: pytest.FixtureRequest, tmp_path: Path) -> E2EResult:
    """Run source-edition render + QA for one golden fixture document."""
    doc_id: str = request.param
    waivers_dir = _write_source_only_waivers(tmp_path, doc_id)
    ctx = _make_ctx(tmp_path, doc_id, qa_config=QAConfig(waivers_dir=str(waivers_dir)))
    _seed_golden_irs(ctx.artifact_store, doc_id)

    render_result = RenderStage().run(ctx, None)
    _register_render_event(ctx, render_result)
    qa_summary = QAStage().run(ctx, None)
    return E2EResult(doc_id=doc_id, render_result=render_result, qa_summary=qa_summary, ctx=ctx)


# ---------------------------------------------------------------------------
# Render validation
# ---------------------------------------------------------------------------


def test_render_pages_exist(e2e_run: E2EResult) -> None:
    """Source-edition render pages are created for every golden page."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        page_dir = (
            e2e_run.ctx.artifact_store.root
            / e2e_run.doc_id
            / "render_page.v1"
            / "page"
            / spec.page_id
        )
        assert list(page_dir.glob("*.json")), f"Missing render page for {spec.page_id}"


def test_render_block_kinds(e2e_run: E2EResult) -> None:
    """Rendered blocks have correct kinds — only renderable IR types appear."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        rp = _read_render_page(e2e_run.ctx.artifact_store, e2e_run.doc_id, spec.page_id)
        expected = [t for t in spec.block_types if t in _RENDERABLE]
        actual = [b.kind for b in rp.blocks]
        assert actual == expected, f"{e2e_run.doc_id}/{spec.page_id}: {expected=}, {actual=}"


def test_render_icon_count(e2e_run: E2EResult) -> None:
    """Icon inline count in render matches golden symbol_count."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        rp = _read_render_page(e2e_run.ctx.artifact_store, e2e_run.doc_id, spec.page_id)
        actual = _count_icons(rp)
        assert actual == spec.symbol_count, (
            f"{e2e_run.doc_id}/{spec.page_id}: expected {spec.symbol_count} icons, got {actual}"
        )


def test_source_map_block_refs(e2e_run: E2EResult) -> None:
    """Source map includes all IR block IDs (including non-rendered blocks)."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        rp = _read_render_page(e2e_run.ctx.artifact_store, e2e_run.doc_id, spec.page_id)
        assert rp.source_map is not None
        assert rp.source_map.block_refs == spec.reading_order


def test_render_page_id_matches(e2e_run: E2EResult) -> None:
    """Render page metadata has the correct page ID."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        rp = _read_render_page(e2e_run.ctx.artifact_store, e2e_run.doc_id, spec.page_id)
        assert rp.page.id == spec.page_id


def test_figure_assets_in_render(e2e_run: E2EResult) -> None:
    """Figure blocks reference assets that exist in render.figures."""
    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        rp = _read_render_page(e2e_run.ctx.artifact_store, e2e_run.doc_id, spec.page_id)
        for block in rp.blocks:
            if isinstance(block, RenderFigureBlock):
                assert block.asset_id in rp.figures, (
                    f"{e2e_run.doc_id}/{spec.page_id}: "
                    f"figure asset {block.asset_id} not in render.figures"
                )


# ---------------------------------------------------------------------------
# QA validation
# ---------------------------------------------------------------------------


def test_qa_non_blocking(e2e_run: E2EResult) -> None:
    """QA is not blocking for curated pages (UNTRANSLATED_TEXT waived)."""
    assert not e2e_run.qa_summary.blocking, (
        f"{e2e_run.doc_id}: QA is blocking — "
        f"errors={e2e_run.qa_summary.counts.error}, "
        f"critical={e2e_run.qa_summary.counts.critical}"
    )
    assert e2e_run.qa_summary.counts.error == 0, f"{e2e_run.doc_id}: unwaived errors remain"


# ---------------------------------------------------------------------------
# Publish validation
# ---------------------------------------------------------------------------


def test_publish_creates_bundle(e2e_run: E2EResult) -> None:
    """Publish stage creates a release bundle with edition=en."""
    result = PublishStage().run(e2e_run.ctx, None)
    assert result.files_published > 0

    release_dir = e2e_run.ctx.artifact_store.root / e2e_run.doc_id / "release"
    manifest_path = release_dir / "en" / "manifest.json"
    assert manifest_path.exists(), "Missing manifest in release bundle"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["edition"] == "en"

    gs = load_golden_set(e2e_run.doc_id, repo_root=REPO_ROOT)
    for spec in gs.pages:
        page_file = release_dir / "en" / "data" / f"render_page.{spec.page_id}.json"
        assert page_file.exists(), f"Missing {spec.page_id} in release bundle"


# ---------------------------------------------------------------------------
# Negative path: blocking QA produces review pack (S5U-205)
# ---------------------------------------------------------------------------


class _BlockingRule:
    """Synthetic QA rule that always emits an ERROR finding."""

    @property
    def name(self) -> str:
        return "e2e_blocking_rule"

    @property
    def layer(self) -> QALayer:
        return QALayer.EXTRACTION

    def evaluate(self, ctx: QAPageContext) -> list[QARecordV1]:
        return [
            QARecordV1(
                qa_id="qa.p0001.e2e_blocking",
                layer=QALayer.EXTRACTION,
                code="E2E_BLOCKING",
                severity=Severity.ERROR,
                message="Simulated blocking error for negative-path E2E test",
                page_id="p0001",
            )
        ]


def test_blocking_qa_produces_review_pack(tmp_path: Path) -> None:
    """When QA finds blocking errors, blocking=True and review pack is generated."""
    doc_id = "multi_column"
    ctx = _make_ctx(tmp_path, doc_id)
    _seed_golden_irs(ctx.artifact_store, doc_id)
    RenderStage().run(ctx, None)

    with patch("atr_pipeline.stages.qa.stage.get_all_rules", return_value=[_BlockingRule()]):
        qa = QAStage().run(ctx, None)

    assert qa.blocking, "QA should be blocking when ERROR findings exist"
    assert qa.counts.error >= 1
    assert qa.review_pack_ref, "Review pack must be generated when blocking"


# ---------------------------------------------------------------------------
# Waiver path: waived finding removes blocking status (S5U-206)
# ---------------------------------------------------------------------------


def test_waiver_removes_blocking(tmp_path: Path) -> None:
    """A waiver matching the blocking finding makes QA non-blocking."""
    doc_id = "multi_column"
    waiver_dir = tmp_path / "waivers"
    waiver_dir.mkdir()
    ws = WaiverSetV1(
        document_id=doc_id,
        waivers=[
            WaiverV1(
                waiver_id="waiver_e2e_001",
                code="E2E_BLOCKING",
                reason="Accepted for E2E negative-path test",
                approved_by="test_harness",
            )
        ],
    )
    (waiver_dir / f"{doc_id}.json").write_text(ws.model_dump_json())
    ctx = _make_ctx(tmp_path, doc_id, qa_config=QAConfig(waivers_dir=str(waiver_dir)))
    _seed_golden_irs(ctx.artifact_store, doc_id)
    RenderStage().run(ctx, None)

    with patch("atr_pipeline.stages.qa.stage.get_all_rules", return_value=[_BlockingRule()]):
        qa = QAStage().run(ctx, None)

    assert not qa.blocking, "Waived ERROR should not block"
    assert qa.waived_counts.error >= 1
    assert qa.review_pack_ref == "", "No review pack when not blocking"

"""S5U-701 — QA stage manifest-scope regression tests.

These tests pin the two cross-subsystem contracts flagged by Codex during
the S5U-701 review:

* ``test_qa_manifest_respects_full_page_set_under_page_filter`` — the
  dead-page-ref rule's suppression set must be derived from the full
  published page manifest, not the ``--pages`` filter subset.
* ``test_qa_manifest_excludes_empty_non_facsimile_pages`` — the
  suppression set must match the web reader's published page set, not
  every EN IR page (the exporter drops non-facsimile pages with no
  renderable blocks).

Split out of ``test_stage.py`` in the same S5U-701 commit to keep that
file under the 400-line ceiling.
"""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
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


def _load_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text())
    return data


def test_qa_manifest_respects_full_page_set_under_page_filter(tmp_path: Path) -> None:
    """S5U-701 (Codex REVISE round 1):

    The dead-page-ref rule's manifest-aware suppression set must be derived
    from the FULL published page manifest, not the ``--pages`` selection.

    Pre-fix: ``QAStage.run`` built ``known_page_numbers`` from
    ``ctx.filter_pages(...)``, so a partial QA run would flag every reference
    to an unselected-but-published page as ``DEAD_PAGE_REF``.  This test
    seeds a second published page (``p0999``) into the EN IR / render /
    RU IR artifact stores, puts a ``p. 999`` reference on the real page's
    render, then runs QA with ``page_filter = {real_page_id}``.  The fix
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
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

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
    """S5U-701 (Codex REVISE round 2):

    The dead-page-ref suppression manifest must match the web reader's
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
    assertion ``len(dead_refs) == 1`` fails with ``0 == 1``.  Verified
    by reverting ``_filter_publishable_pages`` locally and re-running
    the test.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

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

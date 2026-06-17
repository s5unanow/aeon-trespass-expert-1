"""S5U-730 — QA dead-page-ref manifest must align with the web exporter's
image-injection rescue (``scripts/_export_blocks.inject_image_figures``).

Pre-S5U-730: ``QAStage._filter_publishable_pages`` mirrored only the
exporter's pre-injection filter ("render exists AND (facsimile OR
non-empty blocks)").  An article-mode page with zero stored blocks but
extractable PDF imagery is rescued by the exporter at export time;
references to such a page wrongly fired ``DEAD_PAGE_REF``.

Post-S5U-730: ``IngestStage`` emits a ``page_images.v1`` per-page
manifest; ``_filter_publishable_pages`` reads it and includes pages that
the exporter would rescue (i.e. with >=1 image meeting the exporter's
``min_width=100, min_height=100`` threshold).

The three scenarios pinned here mirror the plan §4d enumeration:

* Scenario A — image-injection FP (the bug under fix): empty-render page
  with a 200x200 image is in the suppression manifest and the
  ``DEAD_PAGE_REF`` does NOT fire.
* Scenario B — legitimate dead ref: page with no render and no images is
  not in the manifest; ``DEAD_PAGE_REF`` fires correctly.
* Scenario C — sub-threshold image: empty-render page with only a 60x60
  image is NOT in the manifest (exporter's 100x100 gate would drop it);
  ``DEAD_PAGE_REF`` fires correctly.
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
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
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

from ._render_binding_helpers import rebind_run_render


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="image_manifest_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="image_manifest_run",
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
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
        (TranslationStage(), None),
        (RenderStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def _seed_p0999_pair(ctx: StageContext, real_page_id: str) -> None:
    """Seed EN/RU IR for a synthetic ``p0999`` cross-ref target so the
    dead-page-ref rule has identical IR shape on both editions."""
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


def _seed_empty_render(ctx: StageContext, page_id: str, page_number: int) -> None:
    empty_render = RenderPageV1(
        page=RenderPageMeta(id=page_id, title="Empty", source_page_number=page_number),
        blocks=[],
        source_map=RenderSourceMap(page_id=page_id, block_refs=[]),
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
        data=empty_render,
    )


def _seed_cross_ref_render(ctx: StageContext, page_id: str, target_page: int) -> None:
    ref_render = RenderPageV1(
        page=RenderPageMeta(id=page_id, title="Test", source_page_number=1),
        blocks=[
            RenderParagraphBlock(
                id="b_crossref",
                children=[RenderTextInline(text=f"See rules on p. {target_page} for details")],
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


def _seed_page_images_manifest(
    ctx: StageContext,
    page_id: str,
    page_number: int,
    width_px: int,
    height_px: int,
) -> None:
    """Write a single-image ``page_images.v1`` manifest for *page_id*."""
    manifest = PageImagesV1(
        document_id=ctx.document_id,
        page_id=page_id,
        page_number=page_number,
        images=[
            PageImageEntry(
                image_id=f"{page_id}.img0000",
                width_px=width_px,
                height_px=height_px,
                extension=".png",
            )
        ],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_images.v1",
        scope="page",
        entity_id=page_id,
        data=manifest,
    )


def _records_for(ctx: StageContext, artifact_ref: ArtifactRef) -> list[QARecordV1]:
    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(artifact_ref))
    out: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = ctx.artifact_store.root / ref
        with open(path, encoding="utf-8") as f:
            out.append(QARecordV1.model_validate(json.load(f)))
    return out


def test_qa_manifest_includes_image_only_pages_via_page_images(tmp_path: Path) -> None:
    """Scenario A — exporter image-injection rescue.

    A page whose render is empty but which has a >=100x100 source-PDF
    image is rescued by the exporter (``inject_image_figures``).  QA
    must include such pages in the dead-page-ref suppression manifest.

    Pre-fix: ``_filter_publishable_pages`` only checked render blocks;
    p0999 was excluded; the cross-ref ``p. 999`` fired ``DEAD_PAGE_REF``.
    Post-fix: the ``page_images.v1`` manifest tells QA p0999 has an image
    that the exporter would inject; p0999 enters the suppression manifest;
    the cross-ref does NOT fire.

    Red-before confirmation: commit 5122898 is the parent of this
    branch; pre-fix ``_filter_publishable_pages`` (verified via
    ``git cat-file -e 5122898^{commit}``) only checks render blocks,
    so this test fails with ``len(dead_refs) == 1`` (the unsuppressed
    p. 999 cross-ref).  The post-fix manifest-aware filter adds p0999 to
    the suppression set and the assertion ``dead_refs == []`` holds.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    _seed_p0999_pair(ctx, real_page_id)
    _seed_empty_render(ctx, "p0999", page_number=999)
    _seed_page_images_manifest(ctx, "p0999", page_number=999, width_px=200, height_px=200)
    _seed_cross_ref_render(ctx, real_page_id, target_page=999)
    # S5U-1264 — bind out-of-band render seeds into the run's render index.
    rebind_run_render(ctx, [real_page_id, "p0999"])

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    records = _records_for(ctx, result.artifact_ref)
    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF" and "p. 999" in r.message]
    assert dead_refs == [], (
        "Expected NO DEAD_PAGE_REF for p. 999 when p0999's render is empty "
        "but its page_images.v1 manifest has a 200x200 image (the exporter "
        "would rescue this page via inject_image_figures); got "
        f"{[r.message for r in dead_refs]}"
    )


def test_qa_dead_ref_still_fires_when_no_image_no_render(tmp_path: Path) -> None:
    """Scenario B — legitimate dead ref, no rescue path.

    A reference to ``p. 1234`` where p1234 has no EN IR, no render, and
    no ``page_images.v1`` manifest must still fire ``DEAD_PAGE_REF``.
    The S5U-730 fix must not silently drop legitimate findings.

    Red-before confirmation: N/A — this test pins existing behavior
    (the legitimate-dead-ref case must not regress under the S5U-730
    fix). Reviewer asked to cross-check against ``test_dead_page_ref_rule.py``
    which independently verifies the rule fires when the target is
    absent from ``known_page_numbers``.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    # Reference a page (1234) we never seed at all.
    _seed_cross_ref_render(ctx, real_page_id, target_page=1234)
    # S5U-1264 — bind the out-of-band cross-ref render into the run's index.
    rebind_run_render(ctx, [real_page_id])

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    records = _records_for(ctx, result.artifact_ref)
    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF" and "p. 1234" in r.message]
    assert len(dead_refs) == 1, (
        "Expected DEAD_PAGE_REF for p. 1234 (legitimate dead ref — no "
        "render, no page_images.v1 manifest entry); got "
        f"{[r.message for r in dead_refs]}"
    )


def test_qa_manifest_excludes_pages_with_subthreshold_images(tmp_path: Path) -> None:
    """Scenario C — image too small to rescue.

    Empty-render p0999 with only a 60x60 image must NOT be added to the
    suppression manifest because the exporter's
    ``min_width=100, min_height=100`` gate would drop the image; the
    page is therefore NOT rescued and ``p. 999`` cross-ref must still
    fire as ``DEAD_PAGE_REF``.

    Red-before confirmation: N/A — this test pins post-fix behavior on a
    branch the pre-fix code never exercised (no manifest existed). The
    reviewer's job is to verify the fix's threshold matches
    ``scripts/_export_images.extract_images``'s ``min_width=100,
    min_height=100`` constants.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    real_page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    _seed_p0999_pair(ctx, real_page_id)
    _seed_empty_render(ctx, "p0999", page_number=999)
    _seed_page_images_manifest(ctx, "p0999", page_number=999, width_px=60, height_px=60)
    _seed_cross_ref_render(ctx, real_page_id, target_page=999)
    # S5U-1264 — bind out-of-band render seeds into the run's render index.
    rebind_run_render(ctx, [real_page_id, "p0999"])

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    records = _records_for(ctx, result.artifact_ref)
    dead_refs = [r for r in records if r.code == "DEAD_PAGE_REF" and "p. 999" in r.message]
    assert len(dead_refs) == 1, (
        "Expected DEAD_PAGE_REF for p. 999 when p0999's only image is "
        "60x60 (below the exporter's 100x100 rescue threshold — the "
        "page would NOT be rescued); got "
        f"{[r.message for r in dead_refs]}"
    )

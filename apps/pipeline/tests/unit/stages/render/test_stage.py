"""Tests for the Render stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.render.stage import RenderResult, RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode, StageScope
from atr_schemas.page_ir_v1 import PageIRV1
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
    """Run ingest → extract_native → symbols → structure → translate."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    assert r.artifact_ref is not None
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))

    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success

    r = execute_stage(SymbolsStage(), ctx)
    assert r.success

    r = execute_stage(StructureStage(), ctx)
    assert r.success

    r = execute_stage(TranslationStage(), ctx)
    assert r.success


def test_render_implements_stage_protocol() -> None:
    """RenderStage satisfies the Stage protocol."""
    stage = RenderStage()
    assert isinstance(stage, Stage)
    assert stage.name == "render"
    assert stage.scope == StageScope.DOCUMENT
    # 1.7 → 1.8 (S5U-1554): render metadata now includes page source
    # confidence and facsimile annotations include stable block refs.
    # 1.6 → 1.7 (S5U-737): orphan ``CaptionBlock`` instances now emit a
    # ``RenderCaptionBlock`` instead of being silently dropped at the top of
    # the page_builder block loop. The render_page.v1 artifact shape changes
    # for any page whose IR carries a CaptionBlock without a resolvable
    # owning figure, so cached 1.6 pages must be regenerated. Attached
    # captions continue to fold into RenderFigure.caption unchanged.
    # 1.5 → 1.6 (S5U-739): ``_convert_inline_nodes`` now emits
    # ``RenderFigureRefInline`` for ``FigureRefInline`` IR nodes instead of
    # silently dropping them. The render_page.v1 artifact shape changes for
    # any page whose IR carries a ``figure_ref`` inline (in callouts,
    # paragraphs, list items, headings, figures, or table cells), so cached
    # 1.5 pages must be regenerated.
    # 1.4 → 1.5 (S5U-581): callout blocks now emit ``RenderCalloutBlock``
    # instead of being silently dropped; render_page.v1 payload shape changes
    # for callout-bearing pages, so cached 1.4 pages must be regenerated.
    # 1.3 → 1.4 (S5U-735): RenderSourceMap grew ``document_id`` (populated
    # from page_ir.document_id); the render_page.v1 artifact shape changed,
    # so cached 1.3 pages must be regenerated for QA rules to pick up the
    # real document id.
    assert stage.version == "1.8"


@pytest.mark.slow  # S5U-1230: full-pipeline-chain; excluded from fast pre-commit subset
def test_render_builds_pages(tmp_path: Path) -> None:
    """RenderStage produces render pages after full prerequisite chain."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(RenderStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    render_result = RenderResult.model_validate(data)
    assert render_result.document_id == "walking_skeleton"
    assert render_result.pages_rendered == 1
    assert "p0001" in render_result.page_refs
    assert render_result.page_refs["p0001"].endswith(".json")

    # Verify per-page render artifact was stored
    render_dir = tmp_path / "artifacts" / "walking_skeleton" / "render_page.v1" / "page" / "p0001"
    assert render_dir.exists()
    jsons = list(render_dir.glob("*.json"))
    assert len(jsons) == 1

    # Verify companion artifacts have refs
    assert render_result.glossary_ref != ""
    assert render_result.search_docs_ref != ""
    assert render_result.nav_ref != ""

    # Verify companion artifacts exist on disk
    arts = tmp_path / "artifacts" / "walking_skeleton"
    assert (arts / "glossary_payload.v1").exists()
    assert (arts / "search_docs.v1").exists()
    assert (arts / "nav.v1").exists()


def test_render_raises_without_ir(tmp_path: Path) -> None:
    """RenderStage fails when no IR pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(RenderStage(), ctx)
    assert not result.success
    assert "No IR pages found" in (result.error or "")


def _put_page_ir(ctx: StageContext, *, lang: str, page_id: str) -> None:
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id=page_id,
        page_number=int(page_id.removeprefix("p")),
        language=LanguageCode.EN if lang == "en" else LanguageCode.RU,
        reading_order=[],
        blocks=[],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family=f"page_ir.v1.{lang}",
        scope="page",
        entity_id=page_id,
        data=ir,
    )


def test_render_load_page_ir_prefers_en_for_source_only(tmp_path: Path) -> None:
    """edition=en must not load stale RU IR when both families exist."""
    ctx = _make_ctx(tmp_path)
    ctx.edition = "en"
    _put_page_ir(ctx, lang="ru", page_id="p0001")
    _put_page_ir(ctx, lang="en", page_id="p0001")

    loaded = RenderStage._load_page_ir(ctx, "p0001")

    assert loaded is not None
    ir, lang = loaded
    assert lang == "en"
    assert ir.language == LanguageCode.EN


def test_render_resolve_page_ids_prefers_en_family_for_source_only(tmp_path: Path) -> None:
    """edition=en should enumerate EN IR pages before legacy RU families."""
    ctx = _make_ctx(tmp_path)
    ctx.edition = "en"
    _put_page_ir(ctx, lang="ru", page_id="p0009")
    _put_page_ir(ctx, lang="en", page_id="p0001")

    page_ids = RenderStage._resolve_page_ids(ctx)

    assert page_ids == ["p0001"]


def test_render_extra_cache_inputs_tracks_concepts_toml(tmp_path: Path) -> None:
    """Regression for S5U-583: concepts.toml edits must invalidate render cache.

    The render stage reads configs/glossary/concepts.toml outside
    DocumentBuildConfig. Without ``extra_cache_inputs``, expanding the
    concept registry does not change the cache key and stale glossary
    payloads keep winning.
    """
    ctx = _make_ctx(tmp_path)
    fake_root = tmp_path / "fake_repo"
    (fake_root / "configs" / "glossary").mkdir(parents=True)
    concepts_path = fake_root / "configs" / "glossary" / "concepts.toml"
    ctx.config.repo_root = fake_root

    concepts_path.write_text('version = "1"\nconcepts = []\n')
    empty_key = RenderStage().extra_cache_inputs(ctx)

    concepts_path.write_text(
        'version = "1"\n'
        "[[concepts]]\n"
        'concept_id = "x"\n'
        '[concepts.source]\nlemma = "x"\n'
        '[concepts.target]\nlemma = "X"\n'
    )
    populated_key = RenderStage().extra_cache_inputs(ctx)

    assert empty_key != populated_key
    assert empty_key and populated_key  # both non-empty


def test_render_extra_cache_inputs_missing_concepts_returns_empty(tmp_path: Path) -> None:
    """When concepts.toml is absent, extra_cache_inputs returns no extras."""
    ctx = _make_ctx(tmp_path)
    fake_root = tmp_path / "no_concepts"
    fake_root.mkdir()
    ctx.config.repo_root = fake_root

    assert RenderStage().extra_cache_inputs(ctx) == []

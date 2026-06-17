"""S5U-1229 — QA stage render-load de-duplication.

``QAStage.run`` resolves the publishable page set (which selects+parses every
page's ``render_page.v1``) and then, in the per-page eval loop, loaded the same
render a *second* time. This pins the fix: the publishability filter populates
a render cache that the eval loop reuses, so each page's render is selected and
parsed exactly once per ``run``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

import atr_pipeline.stages.qa.render_binding as render_binding_mod
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
from atr_schemas.source_manifest_v1 import SourceManifestV1

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
    for stage in (
        ExtractNativeStage,
        SymbolsStage,
        StructureStage,
        TranslationStage,
        RenderStage,
    ):
        inp = manifest if stage is ExtractNativeStage else None
        assert execute_stage(stage(), ctx, input_data=inp).success


def test_qa_run_selects_each_render_once(tmp_path: Path, monkeypatch) -> None:
    """Each page's ``render_page.v1`` is selected (and thus parsed) once per run.

    Red-before: prior to S5U-1229 ``QAStage.run`` selected each page's render
    in the publishability filter *and* again in the per-page eval loop — 2
    selections per page. The render cache reuses the filter's result, so the
    count drops to 1 per page. S5U-1264 routes both paths through the single
    per-page render chokepoint ``render_binding.load_run_bound_render``; spying
    on it counts selections per page_id regardless of run-bound vs mtime path.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_ids = sorted(p.name for p in en_dir.iterdir() if p.is_dir())
    assert page_ids, "fixture produced no EN IR pages"

    selections: Counter[str] = Counter()
    real = render_binding_mod.load_run_bound_render

    def _spy(*args: object, **kwargs: object) -> object:
        # one call per page-render selection; keyed by entity page_id
        selections[str(kwargs.get("page_id"))] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(render_binding_mod, "load_run_bound_render", _spy)
    # both call sites import the symbol by name from their own module
    monkeypatch.setattr("atr_pipeline.stages.qa.publishable.load_run_bound_render", _spy)
    monkeypatch.setattr("atr_pipeline.stages.qa.stage.load_run_bound_render", _spy)

    summary = QAStage().run(ctx, None)
    assert summary.document_id == ctx.document_id

    # No page's render is selected more than once.
    over_selected = {pid: n for pid, n in selections.items() if n > 1}
    assert not over_selected, f"renders selected more than once per run: {over_selected}"
    # And every eval'd page WAS selected (cache populated, loop reused it).
    assert set(selections) == set(page_ids)
    assert all(n == 1 for n in selections.values())


def test_qa_run_reuses_cached_none_render(tmp_path: Path, monkeypatch) -> None:
    """A page whose render is absent (cached ``None``) is not re-selected by the
    eval loop — the cache distinguishes "cached None" from "absent from cache"
    via ``in`` membership.

    To force a ``None`` render under S5U-1264 run-binding (where a covered
    ``page_refs`` entry would otherwise load the artifact by ref), delete the
    target page's render artifact entirely so BOTH the run-bound ref load and
    the mtime fallback miss.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_ids = sorted(p.name for p in en_dir.iterdir() if p.is_dir())
    target = page_ids[0]

    render_dir = ctx.artifact_store.root / ctx.document_id / "render_page.v1" / "page" / target
    for f in render_dir.glob("*.json"):
        f.unlink()

    selections: Counter[str] = Counter()
    real = render_binding_mod.load_run_bound_render

    def _spy(*args: object, **kwargs: object) -> object:
        selections[str(kwargs.get("page_id"))] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(render_binding_mod, "load_run_bound_render", _spy)
    monkeypatch.setattr("atr_pipeline.stages.qa.publishable.load_run_bound_render", _spy)
    monkeypatch.setattr("atr_pipeline.stages.qa.stage.load_run_bound_render", _spy)

    QAStage().run(ctx, None)

    # The target's render resolves to None, but it must still be selected at
    # most once (filter populates cache with None; eval loop reads the None).
    assert selections[target] <= 1

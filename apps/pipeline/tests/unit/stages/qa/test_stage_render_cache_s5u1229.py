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

import atr_pipeline.stages.qa.publishable as publishable_mod
import atr_pipeline.stages.qa.stage as qa_stage_mod
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

    Red-before: prior to S5U-1229 ``QAStage.run`` called
    ``load_latest_json_for_edition`` for every page in the publishability filter
    *and* again in the per-page eval loop — 2 selections per page. The render
    cache reuses the filter's result, so the count drops to 1 per page.

    We spy on ``load_latest_json_for_edition`` in BOTH modules that import it
    by name (``publishable`` and ``stage``) and count selections per page_id.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_ids = sorted(p.name for p in en_dir.iterdir() if p.is_dir())
    assert page_ids, "fixture produced no EN IR pages"

    selections: Counter[str] = Counter()
    real = publishable_mod.load_latest_json_for_edition

    def _spy(*args: object, **kwargs: object) -> object:
        # render selections are keyed by entity_id=page_id, schema render_page.v1
        if kwargs.get("schema_family") == "render_page.v1":
            selections[str(kwargs.get("entity_id"))] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(publishable_mod, "load_latest_json_for_edition", _spy)
    monkeypatch.setattr(qa_stage_mod, "load_latest_json_for_edition", _spy)

    summary = QAStage().run(ctx, None)
    assert summary.document_id == ctx.document_id

    # No page's render is selected more than once.
    over_selected = {pid: n for pid, n in selections.items() if n > 1}
    assert not over_selected, f"renders selected more than once per run: {over_selected}"
    # And every eval'd page WAS selected (cache populated, loop reused it).
    assert set(selections) == set(page_ids)
    assert all(n == 1 for n in selections.values())


def test_qa_run_reuses_cached_none_render(tmp_path: Path, monkeypatch) -> None:
    """A page whose render is absent for the edition (cached ``None``) is not
    re-selected by the eval loop — the cache distinguishes "cached None" from
    "absent from cache" via ``in`` membership.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_ids = sorted(p.name for p in en_dir.iterdir() if p.is_dir())
    target = page_ids[0]

    # Make the target page's render unresolvable for an EN-edition run by
    # retagging its render to a sibling edition so the two-tier filter returns
    # None (tier-2 suppressed once a sibling tag exists).
    render_dir = ctx.artifact_store.root / ctx.document_id / "render_page.v1" / "page" / target
    import json

    for f in render_dir.glob("*.json"):
        data = json.loads(f.read_text())
        data["document_version"] = "ru"
        f.write_text(json.dumps(data))
    ctx.edition = "en"

    selections: Counter[str] = Counter()
    real = publishable_mod.load_latest_json_for_edition

    def _spy(*args: object, **kwargs: object) -> object:
        if kwargs.get("schema_family") == "render_page.v1":
            selections[str(kwargs.get("entity_id"))] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(publishable_mod, "load_latest_json_for_edition", _spy)
    monkeypatch.setattr(qa_stage_mod, "load_latest_json_for_edition", _spy)

    QAStage().run(ctx, None)

    # The target's render resolves to None, but it must still be selected at
    # most once (filter populates cache with None; eval loop reads the None).
    assert selections[target] <= 1

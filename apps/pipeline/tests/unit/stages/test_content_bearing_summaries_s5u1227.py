"""S5U-1227 — content-bearing stage cache summaries close the lossy-cache-key class.

The CLI run loop (``cli/commands/run.py``) threads cache integrity across
stages by appending each stage's *summary artifact* content hash to
``upstream_refs``, which feeds the next stage's cache key
(``runner/cache_keys.build_cache_key``). A stage's summary artifact content
hash is derived from the serialized summary model (``ArtifactStore.put_json``
-> ``utils.hashing.content_hash``).

Before this change, ``TranslationResult`` / ``StructureResult`` /
``ExtractLayoutResult`` were *count-only* (``pages_built`` etc.). When upstream
per-page content changed but the counts stayed equal, the summary hash was
unchanged -> the downstream stage cache-hit on stale input. ``RenderResult``
already avoided this with per-page ``page_refs``; these tests assert the three
count-only summaries now mirror that content-bearing shape, and that the
lossy-cache-key class is closed at the summary-hash level.

Each summary's per-page ref is the *content-addressed relative path* of the
per-page artifact (the path embeds the per-page content hash), so the summary
serialization — and therefore the summary artifact's own content hash — changes
whenever any per-page artifact changes, even at a constant page count.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_layout.stage import ExtractLayoutResult, ExtractLayoutStage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.structure.stage import StructureResult, StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationResult, TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="s5u1227_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="s5u1227_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_through_native(ctx: StageContext) -> None:
    """ingest -> extract_native (the prerequisite for extract_layout)."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success


def _run_through_symbols(ctx: StageContext) -> None:
    """ingest -> extract_native -> symbols (the prerequisite for structure)."""
    _run_through_native(ctx)
    r = execute_stage(SymbolsStage(), ctx)
    assert r.success


def _run_through_structure(ctx: StageContext) -> None:
    """...-> structure (the prerequisite for translate)."""
    _run_through_symbols(ctx)
    r = execute_stage(StructureStage(), ctx)
    assert r.success


# --------------------------------------------------------------------------- #
# Part 1a — each summary is content-bearing (page_refs populated).
# --------------------------------------------------------------------------- #


def test_extract_layout_result_carries_page_refs(tmp_path: Path) -> None:
    """ExtractLayoutResult.page_refs maps every processed page to its
    layout_page.v1 content-addressed path.

    Red-before: the count-only ExtractLayoutResult has no page_refs field, so
    page_refs is absent / always empty even with pages processed.
    """
    ctx = _make_ctx(tmp_path)
    _run_through_native(ctx)

    result = ExtractLayoutStage().run(ctx, None)
    assert isinstance(result, ExtractLayoutResult)
    assert result.pages_processed > 0
    assert len(result.page_refs) == result.pages_processed
    for page_id, ref in result.page_refs.items():
        assert ref.startswith(f"walking_skeleton/layout_page.v1/page/{page_id}/")
        assert ref.endswith(".json")


def test_structure_result_carries_page_refs(tmp_path: Path) -> None:
    """StructureResult.page_refs maps every built page to its page_ir.v1.en
    content-addressed path.

    Red-before: the count-only StructureResult has no page_refs field.
    """
    ctx = _make_ctx(tmp_path)
    _run_through_symbols(ctx)

    result = StructureStage().run(ctx, None)
    assert isinstance(result, StructureResult)
    assert result.pages_built > 0
    assert len(result.page_refs) == result.pages_built
    for page_id, ref in result.page_refs.items():
        assert ref.startswith(f"walking_skeleton/page_ir.v1.en/page/{page_id}/")
        assert ref.endswith(".json")


def test_translation_result_carries_page_refs(tmp_path: Path) -> None:
    """TranslationResult.page_refs maps every translated page to its
    page_ir.v1.ru content-addressed path.

    Red-before: the count-only TranslationResult has no page_refs field.
    """
    ctx = _make_ctx(tmp_path)
    _run_through_structure(ctx)

    result = TranslationStage().run(ctx, None)
    assert isinstance(result, TranslationResult)
    assert result.pages_translated > 0
    assert len(result.page_refs) == result.pages_translated
    for page_id, ref in result.page_refs.items():
        assert ref.startswith(f"walking_skeleton/page_ir.v1.ru/page/{page_id}/")
        assert ref.endswith(".json")


# --------------------------------------------------------------------------- #
# Part 1b — the lossy-cache-key class is closed: a summary whose per-page
# content differs at an equal count produces a *different* summary artifact
# content hash (so a different downstream upstream_ref / cache key).
# --------------------------------------------------------------------------- #


def test_downstream_misses_cache_when_upstream_content_changes_same_count() -> None:
    """Two summaries with equal counts but different per-page refs must hash
    differently, so the downstream stage re-keys (no stale cache hit).

    This is the exact lossy-cache-key class S5U-1227 closes: with the old
    count-only summaries the two ``content_hash`` values below would be
    identical (same counts), aliasing the downstream cache key across distinct
    upstream content.

    Red-before: count-only StructureResult has no page_refs, so both dumps are
    ``{document_id, pages_built, total_blocks, hard_pages}`` -> identical hash.
    """
    base = StructureResult(
        document_id="d",
        pages_built=2,
        total_blocks=10,
        hard_pages=0,
        page_refs={
            "p0001": "d/page_ir.v1.en/page/p0001/aaaaaaaaaaaa.json",
            "p0002": "d/page_ir.v1.en/page/p0002/bbbbbbbbbbbb.json",
        },
    )
    # Same counts, but page p0002's per-page content hash changed (re-extraction
    # produced different IR while page/block counts stayed equal).
    changed = StructureResult(
        document_id="d",
        pages_built=2,
        total_blocks=10,
        hard_pages=0,
        page_refs={
            "p0001": "d/page_ir.v1.en/page/p0001/aaaaaaaaaaaa.json",
            "p0002": "d/page_ir.v1.en/page/p0002/cccccccccccc.json",
        },
    )

    base_hash = content_hash(base.model_dump(mode="json"))
    changed_hash = content_hash(changed.model_dump(mode="json"))
    assert base_hash != changed_hash, (
        "Content-bearing summary failed to distinguish changed upstream content "
        "at an equal page count — the lossy-cache-key class is not closed."
    )


def test_summary_hash_stable_when_content_identical() -> None:
    """Identical per-page refs at equal counts hash identically (legitimate
    cache hit preserved — the fix does not over-invalidate).

    Red-before: N/A — no production code change exercised by this assertion
    beyond the page_refs field added in this PR; pins the determinism invariant
    that legitimate cache hits still hit. Reviewer asked to cross-check diff.
    """
    a = TranslationResult(
        document_id="d",
        pages_translated=2,
        validation_warnings=0,
        page_refs={
            "p0001": "d/page_ir.v1.ru/page/p0001/aaaaaaaaaaaa.json",
            "p0002": "d/page_ir.v1.ru/page/p0002/bbbbbbbbbbbb.json",
        },
    )
    b = TranslationResult(
        document_id="d",
        pages_translated=2,
        validation_warnings=0,
        page_refs={
            "p0001": "d/page_ir.v1.ru/page/p0001/aaaaaaaaaaaa.json",
            "p0002": "d/page_ir.v1.ru/page/p0002/bbbbbbbbbbbb.json",
        },
    )
    assert content_hash(a.model_dump(mode="json")) == content_hash(b.model_dump(mode="json"))

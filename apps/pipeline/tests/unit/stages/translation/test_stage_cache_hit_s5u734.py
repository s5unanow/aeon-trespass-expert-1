"""S5U-734 — TranslationStage cache-hit replay regression.

Per ``.claude/rules/pipeline.md`` § "Stage-output cache invalidation":
when a stage gains a new observable side-effect (here, the RU ``PageIRV1``
artifact now carries ``TableRowBlock`` / ``TableCellBlock`` structure
rather than flat inlines) the stage's ``version`` field MUST be bumped
(done: 1.0 → 1.1) **AND** a regression test must exercise the executor's
cache-hit path to assert the side-effect is preserved on cached runs.

This test runs ``TranslationStage`` twice via the executor and asserts
every persisted artifact from the first run remains on disk with
identical bytes after the second (cache-hit) run.

Guarded schema families:

* ``translate`` — the executor-written summary artifact (``TranslationResult``).
* ``translation_meta.v1`` — per-page provenance / source_checksums.
* ``translation_qa_record_set.v1`` — per-page QA findings.
* ``page_ir.v1.ru`` — the RU IR, which is the S5U-734 side-effect: its
  content structure (flat vs. structured tables) changed with this PR.
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1
from tests.unit.stages.qa.test_stage_cache_hit import (
    assert_cache_hit_replays_artifact,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="translation_cache_hit_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="translation_cache_hit_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_prerequisites_excluding_translation(ctx: StageContext) -> None:
    """Run ingest → extract_native → symbols → structure (NOT translation).

    The shared helper in ``test_stage_cache_hit.py`` already runs
    translation as a prerequisite for QA; we need an empty registry for
    ``translate`` so we can observe the miss → hit transition.
    """
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def test_translation_stage_cache_hit_preserves_artifacts(tmp_path: Path) -> None:
    """Second ``execute_stage(TranslationStage(), ctx)`` call must hit the
    cache and leave every first-run artifact on disk, byte-identical.

    If a future PR adds a new persisted side-effect to
    ``TranslationStage.run()`` without bumping ``TranslationStage.version``,
    extend the ``schema_families`` set below to include the new family.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites_excluding_translation(ctx)

    assert_cache_hit_replays_artifact(
        TranslationStage(),
        ctx,
        schema_families={
            "translate",
            "translation_meta.v1",
            "translation_qa_record_set.v1",
            "page_ir.v1.ru",
        },
    )

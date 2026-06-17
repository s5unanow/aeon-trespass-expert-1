"""S5U-1226 — TranslationStage persists ``primary_error`` into translation_meta.

The fallback layer (``services/llm/fallback.py``) sets
``meta.extra["primary_error"]`` on the winning fallback response, but before
this change ``stages/translation/stage.py`` persisted only ``fallback_used`` +
``attempts`` into the ``translation_meta.v1`` artifact — so the real primary
(agy-cli) error was unrecoverable from the run (the S5U-997 blocker).

These tests drive the stage with a translator that returns a real, valid
result whose ``meta.extra`` is shaped like the fallback / non-fallback paths,
then assert the persisted artifact carries the field.

Red-before: with the ``"primary_error"`` line removed from
``stage._translate_page``'s ``meta_data`` dict, ``meta["primary_error"]`` raises
``KeyError`` (field absent), so ``test_primary_error_persisted_on_fallback``
fails. See the PR body for the cited pre-fix excerpt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslationResponse, TranslatorAdapter
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation import stage as translation_stage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1

# S5U-1230: full-pipeline-chain integration tests — excluded from the
# fast pre-commit subset via `-m "not slow"`. CI runs the full suite.
pytestmark = pytest.mark.slow


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


class _ExtraStampingTranslator:
    """Wrap MockTranslator and stamp ``meta.extra`` like the fallback layer."""

    def __init__(self, extra: dict[str, object]) -> None:
        self._inner = MockTranslator()
        self._extra = extra

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        resp = self._inner.translate_batch(batch, model_profile)
        resp.meta.extra.update(self._extra)
        return resp


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="primary_error_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="primary_error_run",
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
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def _load_meta(ctx: StageContext) -> dict[str, object]:
    meta_dir = (
        ctx.artifact_store.root / "walking_skeleton" / "translation_meta.v1" / "page" / "p0001"
    )
    jsons = list(meta_dir.glob("*.json"))
    assert len(jsons) == 1
    return json.loads(jsons[0].read_text())  # type: ignore[no-any-return]


def _patch_translator(monkeypatch: pytest.MonkeyPatch, adapter: TranslatorAdapter) -> None:
    monkeypatch.setattr(
        translation_stage,
        "create_translator",
        lambda *args, **kwargs: adapter,
    )


def test_primary_error_persisted_on_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the fallback path won, the persisted meta carries primary_error."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    _patch_translator(
        monkeypatch,
        _ExtraStampingTranslator(
            {"fallback_used": True, "attempts": 3, "primary_error": "agy-cli boom: rc=1"}
        ),
    )

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    assert meta["fallback_used"] is True
    assert meta["primary_error"] == "agy-cli boom: rc=1"


def test_primary_error_is_null_on_primary_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the non-fallback path primary_error is persisted as ``null``.

    The key must still be present (so downstream readers don't KeyError) but
    carry ``None`` when no fallback occurred.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)
    _patch_translator(
        monkeypatch,
        _ExtraStampingTranslator({"fallback_used": False, "attempts": 1}),
    )

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    assert meta["fallback_used"] is False
    assert meta["primary_error"] is None

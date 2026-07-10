"""S5U-1542 — end-to-end hard-page routing + provenance in the translation stage.

Drives ``TranslationStage`` over synthetic EN IR pages with the mock provider
(no network, no real models) and asserts:

* disabled (default) → ``translation_meta.v1`` is byte-identical to today, no
  ``hardness`` key, model unchanged (AC 2);
* enabled + over-threshold page → routed to ``model_hard``, recorded in
  metadata (AC 3);
* enabled + under-threshold page → routed to ``model_default`` (AC 3);
* hardness provenance is identical across two independent runs (AC 4);
* the executor cache-hit path preserves the hardness metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslationResponse
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.stages.translation import stage as translation_stage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
    XrefInline,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1

# The historical translation_meta.v1 key set (pre-S5U-1542). The disabled
# path must persist exactly these keys — no more, no fewer.
_HISTORICAL_META_KEYS = {
    "batch_id",
    "page_id",
    "prompt_profile",
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "raw_response",
    "source_checksums",
    "fallback_used",
    "attempts",
    "primary_error",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _easy_page() -> PageIRV1:
    """One plain paragraph — scores well below threshold."""
    return PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[ParagraphBlock(block_id="p1", children=[TextInline(text="Simple prose.")])],
        reading_order=["p1"],
    )


def _hard_page() -> PageIRV1:
    """One icon/xref-dense paragraph — scores above threshold, mock-friendly."""
    children: list[object] = [TextInline(text="Gain 1 ")]
    for i in range(4):
        children.append(IconInline(symbol_id=f"sym.progress{i}"))
        children.append(XrefInline(target_section_id=f"s.{i}", label="see"))
        children.append(TextInline(text=" Progress. "))
    return PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[ParagraphBlock(block_id="p1", children=children)],  # type: ignore[arg-type]
        reading_order=["p1"],
    )


def _make_ctx(
    tmp_path: Path,
    *,
    hardness: TranslationHardnessConfig | None,
    run_id: str = "hardness_run",
) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    config.translation.model_default = "mock-default"
    config.translation.model_hard = "mock-hard"
    if hardness is not None:
        config.translation.hardness = hardness
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id=run_id,
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id=run_id,
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _seed_en_ir(ctx: StageContext, page: PageIRV1) -> None:
    ctx.artifact_store.put_json(
        document_id="walking_skeleton",
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page.page_id,
        data=page,
    )


def _load_meta(ctx: StageContext) -> dict[str, object]:
    meta_dir = (
        ctx.artifact_store.root / "walking_skeleton" / "translation_meta.v1" / "page" / "p0001"
    )
    jsons = list(meta_dir.glob("*.json"))
    assert len(jsons) == 1
    return json.loads(jsons[0].read_text())  # type: ignore[no-any-return]


# ── AC 2 — disabled is byte-identical ─────────────────────────────────


def test_disabled_default_has_no_hardness_key(tmp_path: Path) -> None:
    """Default config (hardness OFF) persists the historical key set only."""
    ctx = _make_ctx(tmp_path, hardness=None)
    _seed_en_ir(ctx, _hard_page())  # even a "hard" page is untouched when OFF

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    assert "hardness" not in meta
    assert set(meta) == _HISTORICAL_META_KEYS
    assert meta["model"] == "mock-v1"  # mock ignores model; unchanged


# ── AC 3 — enabled routing ────────────────────────────────────────────


def test_enabled_hard_page_routes_to_model_hard(tmp_path: Path) -> None:
    """An over-threshold page records model_hard as the chosen model."""
    ctx = _make_ctx(tmp_path, hardness=TranslationHardnessConfig(enabled=True, threshold=2.0))
    _seed_en_ir(ctx, _hard_page())

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    assert "hardness" in meta
    hardness = meta["hardness"]
    assert isinstance(hardness, dict)
    assert hardness["is_hard"] is True
    assert hardness["chosen_model"] == "mock-hard"
    assert hardness["threshold"] == 2.0
    assert hardness["signals"]["icon_count"] == 4
    assert hardness["signals"]["xref_count"] == 4


def test_enabled_easy_page_routes_to_model_default(tmp_path: Path) -> None:
    """An under-threshold page records model_default as the chosen model."""
    ctx = _make_ctx(tmp_path, hardness=TranslationHardnessConfig(enabled=True, threshold=2.0))
    _seed_en_ir(ctx, _easy_page())

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    hardness = meta["hardness"]
    assert isinstance(hardness, dict)
    assert hardness["is_hard"] is False
    assert hardness["chosen_model"] == "mock-default"


# ── End-to-end: the hard model actually reaches the adapter ───────────


class _ModelRecordingTranslator:
    """Mock wrapper that reports the model it was constructed with."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._inner = MockTranslator()

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        resp = self._inner.translate_batch(batch, model_profile)
        resp.meta.model = self._model
        return resp


def test_hard_page_adapter_built_with_model_hard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routed hard adapter is constructed from ``model_hard`` end-to-end."""
    ctx = _make_ctx(tmp_path, hardness=TranslationHardnessConfig(enabled=True, threshold=2.0))
    _seed_en_ir(ctx, _hard_page())

    def fake_factory(
        config: TranslationConfig, *, concept_registry: object = None
    ) -> _ModelRecordingTranslator:
        return _ModelRecordingTranslator(config.model_default)

    monkeypatch.setattr(translation_stage, "create_translator", fake_factory)

    result = execute_stage(TranslationStage(), ctx)
    assert result.success

    meta = _load_meta(ctx)
    # The recording adapter stamps meta.model with the model it was built with;
    # for a hard page that is model_hard.
    assert meta["model"] == "mock-hard"
    hardness = meta["hardness"]
    assert isinstance(hardness, dict)
    assert hardness["chosen_model"] == "mock-hard"


# ── AC 4 — reproducibility across independent runs ────────────────────


def test_hardness_metadata_identical_across_runs(tmp_path: Path) -> None:
    """Two independent runs on identical inputs yield identical provenance."""
    cfg = TranslationHardnessConfig(enabled=True, threshold=2.0)

    ctx_a = _make_ctx(tmp_path / "a", hardness=cfg, run_id="run_a")
    _seed_en_ir(ctx_a, _hard_page())
    assert execute_stage(TranslationStage(), ctx_a).success

    ctx_b = _make_ctx(tmp_path / "b", hardness=cfg, run_id="run_b")
    _seed_en_ir(ctx_b, _hard_page())
    assert execute_stage(TranslationStage(), ctx_b).success

    assert _load_meta(ctx_a)["hardness"] == _load_meta(ctx_b)["hardness"]


# ── Cache-hit path preserves the hardness metadata (S5U-662 spirit) ───


def test_cache_hit_preserves_hardness_metadata(tmp_path: Path) -> None:
    """A second executor invocation (cache hit) keeps the hardness artifact.

    The hardness side-effect is gated on ``translation.hardness`` which is part
    of the config hash, so a cache hit only occurs for the same enabled config —
    and the metadata written on the miss run remains on disk.
    """
    ctx = _make_ctx(tmp_path, hardness=TranslationHardnessConfig(enabled=True, threshold=2.0))
    _seed_en_ir(ctx, _hard_page())

    first = execute_stage(TranslationStage(), ctx)
    assert first.success
    before = _load_meta(ctx)["hardness"]

    second = execute_stage(TranslationStage(), ctx)  # cache hit — run() short-circuits
    assert second.success
    after = _load_meta(ctx)["hardness"]

    assert before == after
    assert isinstance(after, dict)
    assert after["is_hard"] is True

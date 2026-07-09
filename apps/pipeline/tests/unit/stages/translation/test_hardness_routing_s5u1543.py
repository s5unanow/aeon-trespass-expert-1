"""S5U-1543 translation-stage hardness routing tests."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.config.models import TranslationHardnessConfig
from atr_pipeline.config.translation_hardness import TranslationHardnessWeights
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import IconInline, PageIRV1, ParagraphBlock, TableBlock, TextInline


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path, *, run_id: str = "hardness_run") -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    config.translation.fallback_provider = ""
    config.translation.model_default = "mock-default"
    config.translation.model_hard = "mock-hard"
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


def _put_easy_page(ctx: StageContext) -> None:
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[TextInline(text="Attack Test", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=ir,
    )


def _put_hard_page(ctx: StageContext) -> None:
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="Gain 1 ", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.fate"),
                    TextInline(text=" Progress.", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.danger"),
                ],
            ),
            TableBlock(block_id="p0001.t001", translatable=False),
        ],
        reading_order=["p0001.b001", "p0001.t001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=ir,
    )


def _enable_hardness(ctx: StageContext, *, threshold: float) -> None:
    ctx.config.translation.hardness = TranslationHardnessConfig(
        enabled=True,
        threshold=threshold,
        icon_density_reference=1.0,
        weights=TranslationHardnessWeights(
            inline_icon_density=1.0,
            table_presence=2.0,
            segment_count=0.0,
            segment_length=0.0,
        ),
    )


def _load_meta(ctx: StageContext) -> dict[str, object]:
    meta_path = ctx.artifact_store.resolve_latest_path(
        document_id=ctx.document_id,
        schema_family="translation_meta.v1",
        scope="page",
        entity_id="p0001",
    )
    assert meta_path is not None
    return json.loads(meta_path.read_text())


def test_disabled_hardness_preserves_legacy_metadata_shape(tmp_path: Path) -> None:
    """Default-disabled hardness writes no new metadata fields."""
    ctx = _make_ctx(tmp_path)
    _put_hard_page(ctx)

    result = TranslationStage().run(ctx, None)

    assert result.pages_translated == 1
    meta = _load_meta(ctx)
    assert set(meta) == {
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
    assert meta["model"] == "mock-v1"


def test_enabled_hard_page_routes_to_model_hard(tmp_path: Path) -> None:
    """A hard page is translated with model_hard and records provenance."""
    ctx = _make_ctx(tmp_path)
    _enable_hardness(ctx, threshold=1.0)
    _put_hard_page(ctx)

    result = TranslationStage().run(ctx, None)

    assert result.pages_translated == 1
    meta = _load_meta(ctx)
    assert meta["model"] == "mock-hard"
    assert meta["chosen_model"] == "mock-hard"
    hardness = meta["hardness"]
    assert isinstance(hardness, dict)
    assert hardness["is_hard"] is True
    assert hardness["threshold"] == 1.0
    assert hardness["score"] == 2.5
    signals = hardness["signals"]
    assert isinstance(signals, dict)
    assert signals["table_presence"]["contribution"] == 2.0
    assert signals["inline_icon_density"]["contribution"] == 0.5


def test_enabled_easy_page_routes_to_model_default(tmp_path: Path) -> None:
    """A below-threshold page stays on model_default and records provenance."""
    ctx = _make_ctx(tmp_path)
    _enable_hardness(ctx, threshold=1.0)
    _put_easy_page(ctx)

    result = TranslationStage().run(ctx, None)

    assert result.pages_translated == 1
    meta = _load_meta(ctx)
    assert meta["model"] == "mock-default"
    assert meta["chosen_model"] == "mock-default"
    hardness = meta["hardness"]
    assert isinstance(hardness, dict)
    assert hardness["is_hard"] is False
    assert hardness["score"] == 0.0


def test_hardness_metadata_reproducible_across_runs(tmp_path: Path) -> None:
    """Identical input/config yields identical translation metadata."""
    ctx_a = _make_ctx(tmp_path / "a", run_id="hardness_run_a")
    ctx_b = _make_ctx(tmp_path / "b", run_id="hardness_run_b")
    _enable_hardness(ctx_a, threshold=1.0)
    _enable_hardness(ctx_b, threshold=1.0)
    _put_hard_page(ctx_a)
    _put_hard_page(ctx_b)

    TranslationStage().run(ctx_a, None)
    TranslationStage().run(ctx_b, None)

    assert _load_meta(ctx_a) == _load_meta(ctx_b)

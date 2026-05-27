# ruff: noqa: RUF001  — Russian examples are the behavior under test.
"""S5U-800 — post-translation Russian style critic stage tests."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.translation.critic_stage import (
    TranslationStyleCriticResult,
    TranslationStyleCriticStage,
)
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode, StageScope
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticPageV1
from tests.unit.stages.qa.test_stage_cache_hit import assert_cache_hit_replays_artifact


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    config.translation.style_critic_provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="style_critic_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="style_critic_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _write_ir_pair(ctx: StageContext, *, ru_text: str = "с великим трепетом") -> None:
    en_ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="blk_001",
                children=[TextInline(text="with great awe", lang=LanguageCode.EN)],
            )
        ],
        reading_order=["blk_001"],
    )
    ru_ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="blk_001",
                children=[TextInline(text=ru_text, lang=LanguageCode.RU)],
            )
        ],
        reading_order=["blk_001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
        data=en_ir,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.ru",
        scope="page",
        entity_id="p0001",
        data=ru_ir,
    )


def test_style_critic_implements_stage_protocol() -> None:
    stage = TranslationStyleCriticStage()
    assert stage.name == "translation_style_critic"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_style_critic_stage_persists_page_findings(tmp_path: Path) -> None:
    """Stage emits a page-local critic JSON artifact after RU translation exists."""
    ctx = _make_ctx(tmp_path)
    _write_ir_pair(ctx)

    result = execute_stage(TranslationStyleCriticStage(), ctx)

    assert result.success
    assert result.artifact_ref is not None
    summary = TranslationStyleCriticResult.model_validate(
        ctx.artifact_store.get_json(result.artifact_ref)
    )
    assert summary.pages_critiqued == 1
    assert summary.findings_count == 1

    data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="translation_style_critic.v1",
        scope="page",
        entity_id="p0001",
    )
    assert data is not None
    page = TranslationStyleCriticPageV1.model_validate(data)
    assert page.findings[0].paragraph_id == "blk_001"
    assert page.findings[0].quote == "с великим трепетом"


def test_style_critic_stage_fails_without_ru_ir(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)

    result = execute_stage(TranslationStyleCriticStage(), ctx)

    assert not result.success
    assert "Run translation stage first" in (result.error or "")


def test_style_critic_cache_hit_preserves_artifacts(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_ir_pair(ctx)

    assert_cache_hit_replays_artifact(
        TranslationStyleCriticStage(),
        ctx,
        schema_families={
            "translation_style_critic",
            "translation_style_critic.v1",
        },
    )

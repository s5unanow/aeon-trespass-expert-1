"""Mock-provider integration coverage for S5U-1555 model routing."""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import IconInline, InlineNode, PageIRV1, ParagraphBlock, TextInline


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _context(tmp_path: Path, *, enabled: bool) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.repo_root = tmp_path
    config.translation.provider = "mock"
    config.translation.fallback_provider = ""
    config.translation.model_default = "mock-easy"
    config.translation.model_hard = "mock-hard"
    config.translation.hardness = TranslationHardnessConfig(
        enabled=enabled,
        threshold=1.0,
        inline_icon_density_weight=4.0,
        cross_reference_density_weight=0.0,
        table_presence_weight=0.0,
        segment_count_weight=0.0,
        segment_length_weight=0.0,
    )
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="hardness_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="hardness_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _page(page_id: str, *, hard: bool) -> PageIRV1:
    children: list[InlineNode] = [TextInline(text="Attack Test", lang=LanguageCode.EN)]
    if hard:
        children.insert(0, IconInline(symbol_id="sym.fate"))
    block_id = f"{page_id}.b001"
    return PageIRV1(
        document_id="walking_skeleton",
        page_id=page_id,
        page_number=int(page_id.removeprefix("p")),
        language=LanguageCode.EN,
        blocks=[ParagraphBlock(block_id=block_id, children=children)],
        reading_order=[block_id],
    )


def _put_page(ctx: StageContext, page: PageIRV1) -> None:
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page.page_id,
        data=page,
    )


def _load_meta(ctx: StageContext, page_id: str) -> tuple[dict[str, object], str]:
    path = ctx.artifact_store.resolve_latest_path(
        document_id=ctx.document_id,
        schema_family="translation_meta.v1",
        scope="page",
        entity_id=page_id,
    )
    assert path is not None
    data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="translation_meta.v1",
        scope="page",
        entity_id=page_id,
    )
    assert data is not None
    return data, path.read_text()


def test_enabled_hardness_routes_hard_and_easy_pages_and_records_metadata(
    tmp_path: Path,
) -> None:
    """The mock response proves which configured primary model handled each batch."""
    ctx = _context(tmp_path, enabled=True)
    _put_page(ctx, _page("p0001", hard=False))
    _put_page(ctx, _page("p0002", hard=True))

    result = TranslationStage().run(ctx, None)

    assert result.pages_translated == 2
    easy_meta, _ = _load_meta(ctx, "p0001")
    hard_meta, _ = _load_meta(ctx, "p0002")
    assert easy_meta["model"] == "mock-easy"
    assert hard_meta["model"] == "mock-hard"
    assert easy_meta["hardness"] == {
        "score": 0.0,
        "signals": {
            "inline_icon_density": 0.0,
            "cross_reference_density": 0.0,
            "table_presence": 0.0,
            "segment_count": 1.0,
            "average_segment_length": 11.0,
        },
        "contributions": {
            "inline_icon_density": 0.0,
            "cross_reference_density": 0.0,
            "table_presence": 0.0,
            "segment_count": 0.0,
            "average_segment_length": 0.0,
        },
        "threshold": 1.0,
        "is_hard": False,
        "chosen_model": "mock-easy",
    }
    assert hard_meta["hardness"]["score"] == 2.0  # type: ignore[index]
    assert hard_meta["hardness"]["is_hard"] is True  # type: ignore[index]
    assert hard_meta["hardness"]["chosen_model"] == "mock-hard"  # type: ignore[index]


def test_disabled_hardness_preserves_legacy_metadata_bytes(tmp_path: Path) -> None:
    """Disabled routing keeps the pre-S5U-1555 adapter call and metadata shape."""
    ctx = _context(tmp_path, enabled=False)
    page = _page("p0001", hard=True)
    _put_page(ctx, page)
    batch = build_translation_batch(page, prompt_profile=ctx.config.translation.prompt_profile)
    response = MockTranslator().translate_batch(batch)
    expected = {
        "batch_id": batch.batch_id,
        "page_id": page.page_id,
        "prompt_profile": batch.prompt_profile,
        "provider": response.meta.provider,
        "model": response.meta.model,
        "input_tokens": response.meta.input_tokens,
        "output_tokens": response.meta.output_tokens,
        "raw_response": response.meta.raw_response,
        "source_checksums": {s.segment_id: s.source_checksum for s in batch.segments},
        "fallback_used": False,
        "attempts": 1,
        "primary_error": None,
    }

    TranslationStage().run(ctx, None)

    meta, raw = _load_meta(ctx, "p0001")
    assert meta == expected
    assert raw == json.dumps(expected, indent=2, ensure_ascii=False) + "\n"
    assert meta["model"] == "mock-v1"
    assert "hardness" not in meta


def test_hardness_metadata_is_reproducible_across_runs(tmp_path: Path) -> None:
    """Identical PageIR and config produce identical routing provenance."""
    metadata: list[dict[str, object]] = []
    for run_name in ("first", "second"):
        ctx = _context(tmp_path / run_name, enabled=True)
        _put_page(ctx, _page("p0001", hard=True))
        TranslationStage().run(ctx, None)
        meta, _ = _load_meta(ctx, "p0001")
        metadata.append(meta)

    assert metadata[0]["hardness"] == metadata[1]["hardness"]


def test_enabling_hardness_invalidates_legacy_page_resume(tmp_path: Path) -> None:
    """A prior default-model result cannot suppress a newly enabled hard route."""
    ctx = _context(tmp_path, enabled=False)
    _put_page(ctx, _page("p0001", hard=True))
    TranslationStage().run(ctx, None)
    legacy_meta, _ = _load_meta(ctx, "p0001")
    assert legacy_meta["model"] == "mock-v1"

    ctx.config.translation.hardness.enabled = True
    TranslationStage().run(ctx, None)

    routed_meta, _ = _load_meta(ctx, "p0001")
    assert routed_meta["model"] == "mock-hard"
    assert routed_meta["hardness"]["is_hard"] is True  # type: ignore[index]

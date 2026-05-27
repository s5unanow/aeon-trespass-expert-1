# ruff: noqa: RUF001  — Russian examples are the behavior under test.
"""S5U-801 — targeted Russian paragraph style repair stage tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageRequest,
    RepairParagraph,
    build_repair_prompt,
    create_russian_style_repair,
)
from atr_pipeline.services.llm.russian_style_repair_codex import CodexRussianStyleRepair
from atr_pipeline.stages.translation.repair_stage import (
    TranslationStyleRepairResult,
    TranslationStyleRepairStage,
)
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode, Severity, StageScope
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline
from atr_schemas.translation_style_critic_v1 import (
    TranslationStyleCriticFindingV1,
    TranslationStyleCriticPageV1,
)
from atr_schemas.translation_style_repair_v1 import TranslationStyleRepairPageV1
from tests.unit.services.llm._codex_cli_helpers import argv_value_after


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    config.translation.style_critic_provider = "mock"
    config.translation.style_repair_provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="style_repair_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="style_repair_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _write_ir_pair(ctx: StageContext) -> None:
    en_ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="blk_flagged",
                children=[TextInline(text="with great awe, see 0001", lang=LanguageCode.EN)],
            ),
            ParagraphBlock(
                block_id="blk_clean",
                children=[TextInline(text="The Argo waits.", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=["blk_flagged", "blk_clean"],
    )
    ru_ir = PageIRV1(
        document_id=ctx.document_id,
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="blk_flagged",
                children=[
                    TextInline(
                        text="Они ждут с великим трепетом у 0001.",
                        lang=LanguageCode.RU,
                    )
                ],
            ),
            ParagraphBlock(
                block_id="blk_clean",
                children=[TextInline(text="«Арго» ждёт у берега.", lang=LanguageCode.RU)],
            ),
        ],
        reading_order=["blk_flagged", "blk_clean"],
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


def _write_critic_findings(ctx: StageContext, findings: list[str] | None = None) -> None:
    paragraph_ids = ["blk_flagged"] if findings is None else findings
    finding_models = [
        TranslationStyleCriticFindingV1(
            paragraph_id=paragraph_id,
            severity=Severity.WARNING,
            quote="с великим трепетом",
            why="Коллокация звучит тяжеловесно.",
            suggestions=["Заменить на «с благоговейным трепетом»."],
        )
        for paragraph_id in paragraph_ids
    ]
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="translation_style_critic.v1",
        scope="page",
        entity_id="p0001",
        data=TranslationStyleCriticPageV1(
            document_id=ctx.document_id,
            page_id="p0001",
            findings=finding_models,
        ),
    )


def _block_text(page: PageIRV1, block_id: str) -> str:
    block = next(block for block in page.blocks if getattr(block, "block_id", "") == block_id)
    children = getattr(block, "children", [])
    return "".join(node.text for node in children if isinstance(node, TextInline))


def _snapshot_artifacts(store_root: Path, schema_family: str) -> dict[Path, bytes]:
    snapshot: dict[Path, bytes] = {}
    for doc_dir in store_root.iterdir():
        if not doc_dir.is_dir():
            continue
        family_dir = doc_dir / schema_family
        if not family_dir.is_dir():
            continue
        for artifact in family_dir.rglob("*.json"):
            snapshot[artifact] = artifact.read_bytes()
    return snapshot


def _assert_cache_hit_replays_artifacts(
    stage: TranslationStyleRepairStage,
    ctx: StageContext,
    schema_families: set[str],
) -> None:
    first = execute_stage(stage, ctx)
    assert first.success, f"first {stage.name} run failed: {first.error!r}"
    assert not first.cached
    assert first.artifact_ref is not None
    first_snapshots = {
        family: _snapshot_artifacts(ctx.artifact_store.root, family) for family in schema_families
    }

    second = execute_stage(stage, ctx)
    assert second.success, f"second {stage.name} run failed: {second.error!r}"
    assert second.cached
    assert second.cache_key == first.cache_key
    assert second.artifact_ref is not None
    assert second.artifact_ref.relative_path == first.artifact_ref.relative_path

    for family, snapshot in first_snapshots.items():
        assert snapshot, f"first run produced no {family} artifacts"
        for path, before in snapshot.items():
            assert path.read_bytes() == before


def test_style_repair_implements_stage_protocol() -> None:
    stage = TranslationStyleRepairStage()
    assert stage.name == "translation_style_repair"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_style_repair_prompt_feeds_local_context_and_critic_findings() -> None:
    finding = TranslationStyleCriticFindingV1(
        paragraph_id="blk_flagged",
        severity=Severity.WARNING,
        quote="с великим трепетом",
        why="Коллокация звучит тяжеловесно.",
        suggestions=["Заменить на «с благоговейным трепетом»."],
    )
    prompt = build_repair_prompt(
        RepairPageRequest(
            document_id="doc",
            page_id="p0001",
            paragraphs=[
                RepairParagraph(
                    paragraph_id="blk_flagged",
                    current_text="Они ждут с великим трепетом у 0001.",
                    source_text="They wait with great awe at 0001.",
                    prev_ru_text="Предыдущий абзац.",
                    next_ru_text="Следующий абзац.",
                    findings=[finding],
                )
            ],
        )
    )

    assert "They wait with great awe at 0001." in prompt
    assert "Они ждут с великим трепетом у 0001." in prompt
    assert "Коллокация звучит тяжеловесно." in prompt
    assert "Repair only the paragraphs listed" in prompt


def test_style_repair_production_config_uses_codex_55_high() -> None:
    config = load_document_config("ato_core_v1_1", repo_root=_repo_root())

    repair = create_russian_style_repair(config.translation)

    assert isinstance(repair, CodexRussianStyleRepair)
    assert repair._model == "gpt-5.5"
    assert repair._reasoning_effort == "high"


def test_codex_style_repair_writes_codex_strict_schema() -> None:
    payload = json.dumps(
        {"document_id": "doc", "page_id": "p0001", "repairs": []},
        ensure_ascii=False,
    )

    def _side(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        schema_path = argv_value_after(argv, "--output-schema")
        assert last_msg_path is not None
        assert schema_path is not None
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        assert "repairs" in schema["required"]
        assert sorted(schema["required"]) == sorted(schema["properties"])
        Path(last_msg_path).write_text(payload, encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    repair = CodexRussianStyleRepair(model="gpt-5.5", reasoning_effort="high")
    request = RepairPageRequest(document_id="doc", page_id="p0001", paragraphs=[])

    with patch(
        "atr_pipeline.services.llm.russian_style_repair_codex.subprocess.run",
        side_effect=_side,
    ):
        response = repair.repair_page(request)

    assert response.result.repairs == []


def test_style_repair_changes_only_flagged_paragraph_and_reports_ids(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_ir_pair(ctx)
    _write_critic_findings(ctx)

    result = execute_stage(TranslationStyleRepairStage(), ctx)

    assert result.success
    assert result.artifact_ref is not None
    summary = TranslationStyleRepairResult.model_validate(
        ctx.artifact_store.get_json(result.artifact_ref)
    )
    assert summary.pages_seen == 1
    assert summary.paragraphs_repaired == 1

    page_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="translation_style_repair.v1",
        scope="page",
        entity_id="p0001",
    )
    assert page_data is not None
    report = TranslationStyleRepairPageV1.model_validate(page_data)
    assert report.repaired_paragraph_ids == ["blk_flagged"]
    assert report.changes[0].before_text == "Они ждут с великим трепетом у 0001."
    assert report.changes[0].after_text == "Они ждут с благоговейным трепетом у 0001."
    assert report.post_repair_style_qa_count == 0

    ru_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.ru",
        scope="page",
        entity_id="p0001",
    )
    assert ru_data is not None
    ru_ir = PageIRV1.model_validate(ru_data)
    assert _block_text(ru_ir, "blk_flagged") == "Они ждут с благоговейным трепетом у 0001."
    assert _block_text(ru_ir, "blk_clean") == "«Арго» ждёт у берега."


def test_style_repair_no_findings_emits_empty_report_without_churn(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_ir_pair(ctx)
    _write_critic_findings(ctx, findings=[])

    result = execute_stage(TranslationStyleRepairStage(), ctx)

    assert result.success
    assert result.artifact_ref is not None
    summary = TranslationStyleRepairResult.model_validate(
        ctx.artifact_store.get_json(result.artifact_ref)
    )
    assert summary.paragraphs_repaired == 0

    page_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="translation_style_repair.v1",
        scope="page",
        entity_id="p0001",
    )
    assert page_data is not None
    report = TranslationStyleRepairPageV1.model_validate(page_data)
    assert report.repaired_paragraph_ids == []
    assert report.changes == []


def test_style_repair_cache_hit_preserves_artifacts(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    _write_ir_pair(ctx)
    _write_critic_findings(ctx)

    _assert_cache_hit_replays_artifacts(
        TranslationStyleRepairStage(),
        ctx,
        schema_families={
            "translation_style_repair",
            "translation_style_repair.v1",
            "page_ir.v1.ru",
        },
    )

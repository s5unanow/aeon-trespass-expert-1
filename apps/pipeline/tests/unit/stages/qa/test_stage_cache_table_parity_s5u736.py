"""S5U-736 — QA stage version bump invalidates prior-version cached events.

Protects the ``.claude/rules/pipeline.md`` § "Stage-output cache
invalidation" invariant: when the new ``table_structure_parity`` rule
lands and ``QAStage.version`` is bumped from 1.6 to 1.7, cached events
written under the prior 1.6 cache key must NOT hit — otherwise the new
``TABLE_PARITY_*`` records never emit on documents that already ran
under the prior version.

Scenario:

1. Seed paired EN/RU IRs with a structured ``TableBlock`` whose RU side
   is missing a row (``TABLE_PARITY_ROW_COUNT_MISMATCH`` shape).
2. Forge a 'completed' QAStage event under the prior 1.6 cache key.
3. Run ``execute_stage(QAStage(), ctx)``.  Because the live cache key
   uses ``QAStage.version == "1.7"``, the forged 1.6 event is NOT a
   hit, the stage runs, and the parity record is emitted.

If someone reverts the bump to 1.6 the forged event's key matches the
live key; the executor short-circuits with the synthetic dead artifact
ref and the assertion below (``parity`` record present) fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.cache_keys import build_cache_key
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
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
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
        run_id="cache_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="cache_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_pipeline(ctx: StageContext) -> None:
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
        (TranslationStage(), None),
        (RenderStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def _build_paired_irs(page_id: str, doc_id: str) -> tuple[PageIRV1, PageIRV1]:
    """Build EN/RU IRs where the RU table is missing a row."""

    def _table(suffix: str, row_count: int) -> TableBlock:
        rows: list[TableRowBlock] = []
        for r in range(row_count):
            rows.append(
                TableRowBlock(
                    block_id=f"{page_id}.b001.r{r}",
                    cells=[
                        TableCellBlock(
                            block_id=f"{page_id}.b001.r{r}.c{c}",
                            children=[TextInline(text=f"{suffix}-r{r}c{c}")],
                        )
                        for c in range(2)
                    ],
                )
            )
        return TableBlock(
            block_id=f"{page_id}.b001",
            children=list(rows),  # type: ignore[arg-type]
        )

    en_ir = PageIRV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=1,
        language=LanguageCode.EN,
        blocks=[_table("en", 2)],  # type: ignore[list-item]
        reading_order=[f"{page_id}.b001"],
    )
    ru_ir = PageIRV1(
        document_id=doc_id,
        page_id=page_id,
        page_number=1,
        language=LanguageCode.RU,
        blocks=[_table("ru", 1)],  # type: ignore[list-item]
        reading_order=[f"{page_id}.b001"],
    )
    return en_ir, ru_ir


def _seed_paired_irs(ctx: StageContext, page_id: str) -> None:
    en_ir, ru_ir = _build_paired_irs(page_id, ctx.document_id)
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
        data=en_ir,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.ru",
        scope="page",
        entity_id=page_id,
        data=ru_ir,
    )


def _forge_prior_version_event(ctx: StageContext, prior_version: str) -> str:
    """Write a 'completed' QAStage event under a prior version's cache key."""
    qa = QAStage()
    i_hashes: list[str] = []
    if ctx.page_filter:
        i_hashes.append("page_filter:" + "|".join(sorted(ctx.page_filter)))
    prior_key = build_cache_key(
        stage_name=qa.name,
        stage_version=prior_version,
        schema_version="v1",
        config_hash=content_hash(ctx.config.model_dump(mode="json")),
        input_hashes=i_hashes,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name=qa.name,
        scope=qa.scope.value,
        entity_id=ctx.document_id,
        cache_key=prior_key,
    )
    fake_ref = "walking_skeleton/qa/document/walking_skeleton/deadbeef.json"
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=fake_ref,
        duration_ms=0,
    )
    return prior_key


def _records_for(ctx: StageContext, artifact_ref: object) -> list[QARecordV1]:
    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(artifact_ref))  # type: ignore[arg-type]
    import json as _json

    out: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = ctx.artifact_store.root / ref  # type: ignore[operator]
        with open(path, encoding="utf-8") as f:
            out.append(QARecordV1.model_validate(_json.load(f)))
    return out


def test_version_bump_invalidates_prior_qa_cache_for_table_parity(tmp_path: Path) -> None:
    """S5U-736 cache-invariance — a prior-version (1.6) cached QA event
    must NOT hit when ``QAStage.version`` is bumped to 1.7 for the
    table_structure_parity rule.

    If the bump is reverted (version back to 1.6), the forged 1.6 event's
    cache key matches the live cache key, ``execute_stage`` returns a
    cached StageResult pointing at the synthetic dead artifact ref, and
    the assertion below (``parity`` record present) fails.
    """
    ctx = _make_ctx(tmp_path)
    _run_pipeline(ctx)

    page_id = "p0001"
    _seed_paired_irs(ctx, page_id)
    ctx.page_filter = frozenset({page_id})

    prior_key = _forge_prior_version_event(ctx, prior_version="1.6")

    qa_result = execute_stage(QAStage(), ctx)
    assert qa_result.success
    assert qa_result.artifact_ref is not None
    assert qa_result.cache_key != prior_key, (
        "QAStage cache key collided with the forged 1.6 event — "
        "version bump did not differentiate the key space."
    )
    assert not qa_result.cached, (
        "QAStage.execute_stage should have missed the 1.6 cached event; "
        "a cache hit here means the version bump is ineffective."
    )
    records = _records_for(ctx, qa_result.artifact_ref)
    parity = [r for r in records if r.code.startswith("TABLE_PARITY_")]
    assert any(r.code == "TABLE_PARITY_ROW_COUNT_MISMATCH" for r in parity), (
        "Post-bump QA run did not emit TABLE_PARITY_ROW_COUNT_MISMATCH. "
        "Either the version bump is missing (so the 1.6 event hit), the "
        "rule is not wired in the registry, or the rule's row-count "
        f"check drifted. Got codes: {[r.code for r in records]}"
    )

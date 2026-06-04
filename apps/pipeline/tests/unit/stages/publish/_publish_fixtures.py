"""Shared fixtures for the Publish-stage test suite.

Factored out so ``test_publish_stage.py`` (gate behavior) and
``test_publish_draft_label.py`` (S5U-894 on-disk draft label) share one copy of
the context builder, the full-pipeline prerequisite runner, and the blocking-QA
summary seeder without either file exceeding the 400-line budget.
"""

from __future__ import annotations

import json
from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import record_stage_finish, record_stage_start
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.source_manifest_v1 import SourceManifestV1


def repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=repo_root())
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
        repo_root=repo_root(),
    )


def run_prerequisites(ctx: StageContext) -> None:
    """Run ingest -> ... -> qa."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))

    r = execute_stage(ExtractNativeStage(), ctx, input_data=manifest)
    assert r.success

    r = execute_stage(SymbolsStage(), ctx)
    assert r.success

    r = execute_stage(StructureStage(), ctx)
    assert r.success

    r = execute_stage(TranslationStage(), ctx)
    assert r.success

    r = execute_stage(RenderStage(), ctx)
    assert r.success

    from atr_pipeline.stages.qa.stage import QAStage

    r = execute_stage(QAStage(), ctx)
    assert r.success


def _blocking_record(code: str, page_id: str) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{code}.{page_id}",
        layer=QALayer.STRUCTURE,
        severity=Severity.ERROR,
        code=code,
        page_id=page_id,
        waived=False,
    )


def seed_qa_summary(ctx: StageContext, summary: QASummaryV1) -> None:
    """Write a QASummaryV1 artifact + a 'qa' stage event for the run.

    Lets the publish gate resolve a synthetic (e.g. blocking) QA summary without
    needing the document's real QA to be blocking. Records referenced by
    ``summary.record_refs`` are presumed already written by the caller.
    """
    ref = ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="qa",
        scope="document",
        entity_id=ctx.document_id,
        data=summary,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name="qa",
        scope="document",
        entity_id=ctx.document_id,
        cache_key=f"seed_qa_{ctx.run_id}",
    )
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=ref.relative_path,
    )


def seed_blocking_summary(ctx: StageContext) -> QASummaryV1:
    """Seed a blocking QA summary with one named blocking record. Returns it."""
    rec = _blocking_record("GLUED_TEXT", "p0007")
    rec_ref = ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="qa_record.v1",
        scope="page",
        entity_id="p0007",
        data=rec,
    )
    summary = QASummaryV1(
        document_id=ctx.document_id,
        run_id=ctx.run_id,
        blocking=True,
        record_refs=[rec_ref.relative_path],
        review_pack_ref="walking_skeleton/review_pack.v1/document/walking_skeleton/rp.json",
    )
    seed_qa_summary(ctx, summary)
    return summary


def read_manifest(tmp_path: Path, edition: str = "ru") -> dict[str, object]:
    """Read the published BuildManifestV1 for *edition* off disk."""
    manifest_path = (
        tmp_path / "artifacts" / "walking_skeleton" / "release" / edition / "manifest.json"
    )
    return json.loads(manifest_path.read_text())  # type: ignore[no-any-return]

"""Tests for the QA stage."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.qa.user_feedback import persist_submissions
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, StageScope
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
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
        repo_root=_repo_root(),
    )


def _run_prerequisites(ctx: StageContext) -> None:
    """Run ingest → extract_native → symbols → structure → translate → render."""
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


def test_qa_implements_stage_protocol() -> None:
    """QAStage satisfies the Stage protocol."""
    stage = QAStage()
    assert isinstance(stage, Stage)
    assert stage.name == "qa"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_qa_persists_summary_clean_pipeline(tmp_path: Path) -> None:
    """QAStage persists a QASummaryV1 with no blocking issues."""
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    summary = QASummaryV1.model_validate(data)
    assert summary.document_id == "walking_skeleton"
    assert summary.run_id == "test_run"
    assert summary.blocking is False
    assert summary.counts.error == 0
    assert summary.counts.critical == 0
    assert summary.record_refs == []


def test_qa_raises_without_en_ir(tmp_path: Path) -> None:
    """QAStage fails when no EN IR pages available."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(QAStage(), ctx)
    assert not result.success
    assert "No EN IR pages found" in (result.error or "")


def test_qa_picks_up_user_feedback_for_current_edition(tmp_path: Path) -> None:
    """Ingested user feedback surfaces through QASummaryV1 + record_refs.

    Regression for S5U-605: previously feedback was persisted to a flat
    directory the QA stage never read. This asserts the full loop-closure:
    ingest → ArtifactStore → QA stage → summary/records/review-pack.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    # Discover a page the pipeline actually produced so the feedback is
    # attached to a real page. QAStage filters to pages with EN IR.
    en_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
    page_id = sorted(p.name for p in en_dir.iterdir() if p.is_dir())[0]

    submissions = [
        (
            FeedbackSubmissionV1.model_validate(
                {
                    "document_id": ctx.document_id,
                    "edition": ctx.edition if ctx.edition in ("en", "ru") else "ru",
                    "page_id": page_id,
                    "issue_type": "translation",
                    "note": "wrong term",
                    "url": "",
                    "user_agent": "",
                    "timestamp": "2026-04-18T12:34:56.000Z",
                }
            ),
            "sample.json",
        ),
    ]
    persist_submissions(store=ctx.artifact_store, submissions=submissions)

    # The QA stage's default edition is "all"; use the same edition we
    # submitted against so the loader finds it.
    ctx.edition = submissions[0][0].edition

    result = execute_stage(QAStage(), ctx)
    assert result.success
    assert result.artifact_ref is not None

    summary = QASummaryV1.model_validate(ctx.artifact_store.get_json(result.artifact_ref))
    # user_feedback is info-level and therefore non-blocking.
    assert summary.blocking is False

    # Resolve the referenced QARecord files off disk (ArtifactStore uses
    # ``relative_path`` refs rooted at the store root).
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        record_path = ctx.artifact_store.root / ref
        records.append(QARecordV1.model_validate(_load_json(record_path)))
    user_feedback_records = [r for r in records if r.layer == QALayer.USER_FEEDBACK]
    assert len(user_feedback_records) == 1
    rec = user_feedback_records[0]
    assert rec.page_id == page_id
    assert rec.code == "USER_FEEDBACK_TRANSLATION"
    assert summary.counts.info >= 1


def _load_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text())  # type: ignore[no-any-return]

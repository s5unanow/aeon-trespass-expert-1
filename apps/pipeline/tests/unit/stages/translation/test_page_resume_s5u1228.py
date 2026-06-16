"""S5U-1228 — per-page failure resume for TranslationStage.

Before S5U-1228 a single failed page raised out of ``TranslationStage.run()``;
the executor recorded the event as ``status='failed'`` so the retry cache-missed
and re-translated *every* page from scratch — discarding the LLM spend already
incurred for completed pages. For the 83-page RU edition (S5U-997) that is hours
lost to one transient failure.

These tests pin the resume behaviour:

* ``test_resume_skips_completed_pages`` — happy path: page 2 of 3 raises on the
  first attempt (pages crash mid-run); the retry re-translates ONLY pages 2 & 3
  and resumes page 1 from its persisted record (the LLM is not re-invoked for
  page 1).
* ``test_corrupt_resume_state_falls_back_to_retranslate`` — a corrupt/partial
  ``translation_resume.v1`` record yields ``None`` from ``load_resume_state`` and
  the page is re-translated without crashing (fail-safe).
* ``test_resume_state_invalidated_by_changed_en_ir`` — a resume record whose
  ``en_ir_content_hash`` no longer matches the current EN IR is NOT reused
  (a changed EN source never reuses a stale RU translation).
* ``test_resume_skipped_when_ru_ir_missing`` — a valid record whose referenced
  RU IR artifact was cleaned up is NOT reused (dangling-ref self-heal).

The cache-hit replay invariant (pipeline.md clause 2) for the new
``translation_resume.v1`` artifact is exercised in
``test_stage_cache_hit_s5u734.py`` (schema_families extended there).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslationResponse
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.stages.translation.page_state import (
    RESUME_SCHEMA_FAMILY,
    PageResumeState,
    en_ir_content_hash,
    load_resume_state,
)
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.store.atomic_write import atomic_write_text
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="resume_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="resume_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _put_en_ir(ctx: StageContext, page_id: str, *, text: str = "Attack Test") -> None:
    """Inject a minimal one-paragraph EN page IR for *page_id*."""
    ir = PageIRV1(
        document_id=ctx.document_id,
        page_id=page_id,
        page_number=int(page_id.removeprefix("p")),
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id=f"{page_id}.b001",
                children=[TextInline(text=text, lang=LanguageCode.EN)],
            ),
        ],
        reading_order=[f"{page_id}.b001"],
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
        data=ir,
    )


class _CountingTranslator(MockTranslator):
    """Mock translator that records which batches it is asked to translate and
    can be configured to raise once on a chosen ``page_id``.

    ``batch_id`` embeds the page id (the planner builds it from the page), so
    we track translated pages by parsing the batch's first segment's page from
    the recorded calls. Simpler: we record the batch_id list and assert against
    it by substring.
    """

    def __init__(self, *, fail_on_batch_substr: str | None = None) -> None:
        self.translated_batches: list[str] = []
        self._fail_on = fail_on_batch_substr
        self._raised = False

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        if self._fail_on is not None and not self._raised and self._fail_on in batch.batch_id:
            self._raised = True
            msg = f"simulated LLM failure on {batch.batch_id}"
            raise RuntimeError(msg)
        self.translated_batches.append(batch.batch_id)
        return super().translate_batch(batch, model_profile)


def _batch_id_for_page(ctx: StageContext, page_id: str) -> str:
    """Resolve the planner's batch_id for *page_id* (used as the fail key)."""
    from atr_pipeline.stages.translation.planner import build_translation_batch

    en_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id=page_id,
    )
    assert en_data is not None
    en_ir = PageIRV1.model_validate(en_data)
    return build_translation_batch(en_ir).batch_id


def test_resume_skips_completed_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Page 2 of 3 fails on the first attempt; the retry resumes page 1 from
    its persisted record (LLM not re-invoked) and re-translates 2 & 3.

    Without the resume mechanism the retry would call ``translate_batch`` for
    page 1 again — the exact LLM-spend waste S5U-1228 fixes.
    """
    ctx = _make_ctx(tmp_path)
    for pid in ("p0001", "p0002", "p0003"):
        _put_en_ir(ctx, pid)

    p2_batch_id = _batch_id_for_page(ctx, "p0002")

    # --- First attempt: page 2 raises mid-run. ---
    first = _CountingTranslator(fail_on_batch_substr=p2_batch_id)
    monkeypatch.setattr(
        "atr_pipeline.stages.translation.stage.create_translator",
        lambda *a, **k: first,
    )
    with pytest.raises(RuntimeError, match="simulated LLM failure"):
        TranslationStage().run(ctx, None)

    # Only page 1 completed (page 2 raised before persisting). Its resume
    # record must be on disk.
    assert first.translated_batches == [_batch_id_for_page(ctx, "p0001")], (
        f"first attempt should have translated only page 1, got {first.translated_batches}"
    )
    resume_p1 = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family=RESUME_SCHEMA_FAMILY,
        scope="page",
        entity_id="p0001",
    )
    assert resume_p1 is not None, "page 1 should have a persisted resume record"

    # --- Retry: fresh translator, no failure. ---
    second = _CountingTranslator()
    monkeypatch.setattr(
        "atr_pipeline.stages.translation.stage.create_translator",
        lambda *a, **k: second,
    )
    result = TranslationStage().run(ctx, None)

    # Page 1 must NOT be re-translated (resumed from cache); pages 2 & 3 are.
    p1_batch = _batch_id_for_page(ctx, "p0001")
    assert p1_batch not in second.translated_batches, (
        "page 1 was re-translated on retry — resume did not skip the completed page"
    )
    assert _batch_id_for_page(ctx, "p0002") in second.translated_batches
    assert _batch_id_for_page(ctx, "p0003") in second.translated_batches
    assert len(second.translated_batches) == 2, (
        f"retry should translate exactly pages 2 & 3, got {second.translated_batches}"
    )

    # The final result still covers all three pages, page_refs intact (S5U-1227).
    assert result.pages_translated == 3
    assert set(result.page_refs) == {"p0001", "p0002", "p0003"}
    for ref in result.page_refs.values():
        assert (ctx.artifact_store.root / ref).exists()


def test_corrupt_resume_state_falls_back_to_retranslate(tmp_path: Path) -> None:
    """A corrupt ``translation_resume.v1`` record must be ignored (fail-safe):
    ``load_resume_state`` returns ``None`` and the page re-translates."""
    ctx = _make_ctx(tmp_path)
    _put_en_ir(ctx, "p0001")
    en_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
    )
    assert en_data is not None
    en_hash = en_ir_content_hash(PageIRV1.model_validate(en_data))

    # Write a garbage resume record (not valid JSON for the schema).
    resume_dir = ctx.artifact_store.root / ctx.document_id / RESUME_SCHEMA_FAMILY / "page" / "p0001"
    atomic_write_text(resume_dir / "deadbeef00.json", "{ this is not valid json ]")

    state = load_resume_state(ctx, "p0001", expected_en_hash=en_hash)
    assert state is None, "corrupt resume record must yield None (fail-safe)"

    # End-to-end: stage still translates the page without crashing.
    result = TranslationStage().run(ctx, None)
    assert result.pages_translated == 1
    assert "p0001" in result.page_refs


def test_resume_state_invalidated_by_changed_en_ir(tmp_path: Path) -> None:
    """A resume record whose EN IR hash no longer matches is NOT reused —
    a changed EN source must never reuse a stale RU translation."""
    ctx = _make_ctx(tmp_path)
    _put_en_ir(ctx, "p0001", text="Attack Test")

    # Persist a resume record keyed to a DIFFERENT (stale) EN hash.
    resume = PageResumeState(
        page_id="p0001",
        en_ir_content_hash="staleHASH000",
        ru_ir_ref="walking_skeleton/page_ir.v1.ru/page/p0001/abc123def456.json",
        warning_count=0,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family=RESUME_SCHEMA_FAMILY,
        scope="page",
        entity_id="p0001",
        data=resume,
    )

    en_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
    )
    assert en_data is not None
    current_hash = en_ir_content_hash(PageIRV1.model_validate(en_data))
    assert current_hash != "staleHASH000"

    state = load_resume_state(ctx, "p0001", expected_en_hash=current_hash)
    assert state is None, "stale-hash resume record must not be reused"


def test_resume_skipped_when_ru_ir_missing(tmp_path: Path) -> None:
    """A valid resume record whose referenced RU IR artifact is gone (e.g.
    ``make clean`` left the record but removed artifacts) must NOT be reused."""
    ctx = _make_ctx(tmp_path)
    _put_en_ir(ctx, "p0001")
    en_data = ctx.artifact_store.load_latest_json(
        document_id=ctx.document_id,
        schema_family="page_ir.v1.en",
        scope="page",
        entity_id="p0001",
    )
    assert en_data is not None
    en_hash = en_ir_content_hash(PageIRV1.model_validate(en_data))

    # Record points at a RU IR that was never written.
    resume = PageResumeState(
        page_id="p0001",
        en_ir_content_hash=en_hash,
        ru_ir_ref="walking_skeleton/page_ir.v1.ru/page/p0001/missing00000.json",
        warning_count=0,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family=RESUME_SCHEMA_FAMILY,
        scope="page",
        entity_id="p0001",
        data=resume,
    )

    state = load_resume_state(ctx, "p0001", expected_en_hash=en_hash)
    assert state is None, "resume record with dangling RU IR ref must not be reused"

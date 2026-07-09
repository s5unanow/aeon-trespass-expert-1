"""Translation stage — translate EN IR pages to RU using an LLM adapter."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_pipeline.services.llm.factory import create_translator
from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.translation.grouping import (
    expand_grouped_batch,
    expand_grouped_result,
)
from atr_pipeline.stages.translation.hardness import compute_hardness
from atr_pipeline.stages.translation.page_state import (
    en_ir_content_hash,
    load_resume_state,
    persist_resume_state,
)
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.rematerialize import rematerialize_ru_blocks
from atr_pipeline.stages.translation.validator import validate_translation
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.enums import LanguageCode, StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_qa_record_set_v1 import TranslationQARecordSetV1
from atr_schemas.translation_result_v1 import TranslationResultV1


class TranslationResult(BaseModel):
    """Summary of translation across all pages.

    ``page_refs`` maps each translated ``page_id`` to the content-addressed
    relative path of its RU ``page_ir.v1.ru`` artifact (the path embeds the
    per-page content hash). This makes the summary content-bearing rather than
    count-only: its own content hash — threaded into the next stage's cache key
    via ``upstream_refs`` — changes whenever any per-page RU IR changes, even at
    an unchanged page count. Mirrors ``RenderResult.page_refs`` (S5U-1227).
    """

    document_id: str
    pages_translated: int = Field(ge=0)
    validation_warnings: int = Field(ge=0)
    page_refs: dict[str, str] = Field(default_factory=dict)


def _expand_grouped_translation_batch(batch: TranslationBatchV1) -> TranslationBatchV1:
    """Return a block-addressable batch for validation/rematerialization."""
    return expand_grouped_batch(batch)


def _expand_grouped_translation_result(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> TranslationResultV1:
    """Return a block-addressable result by splitting narrative-group outputs."""
    return expand_grouped_result(batch, result)


class TranslationStage:
    """Translate EN page IR to RU using an LLM adapter.

    Reads EN ``PageIRV1`` artifacts from the store, creates a
    ``TranslationBatchV1`` per page, translates via the configured
    provider, validates the result, and stores RU ``PageIRV1`` artifacts.
    """

    @property
    def name(self) -> str:
        return "translate"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        # S5U-776 — narrative prose now uses grouped translation units and
        # split-back rematerialization (1.1 -> 1.2; cached per-block re-execute).
        # S5U-871 — validator now emits TRANSLATION_MISSING_SEGMENT /
        # TRANSLATION_DUPLICATE_SEGMENT records into the persisted
        # translation_qa_record_set.v1 artifact; bumped from 1.2 so cached
        # pages re-run and surface the new coverage findings.
        # S5U-1226 — translation_meta.v1 now persists ``primary_error`` (the
        # fallback provider's pre-fallback error, set by FallbackTranslator).
        # Bumped from 1.3 so cached pages re-run and the field is no longer
        # silently absent on pre-existing runs (the S5U-997 blocker).
        # S5U-1227 1.4 -> 1.5: TranslationResult carries content-bearing
        # page_refs (was count-only), so downstream stages re-key on changed RU
        # IR even at an unchanged page count. Per .claude/rules/pipeline.md (S5U-662).
        # S5U-1228 1.5 -> 1.6: run() now persists a per-page
        # translation_resume.v1 record (new observable side-effect) enabling
        # mid-run failure resume. Bumped so cached pages re-run and emit the
        # resume artifact. Per .claude/rules/pipeline.md (S5U-662).
        return "1.6"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> TranslationResult:
        concept_reg = self._load_concept_registry(ctx)
        translator = create_translator(ctx.config.translation, concept_registry=concept_reg)
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))

        pages_translated = 0
        total_warnings = 0
        page_refs: dict[str, str] = {}

        for page_id in page_ids:
            en_ir = self._load_en_ir(ctx, page_id)
            if en_ir is None:
                ctx.logger.warning("Skipping %s: missing EN IR", page_id)
                continue

            warnings, ru_ir_ref = self._process_page(
                ctx,
                en_ir,
                page_id,
                translator,
                concept_reg,
            )
            pages_translated += 1
            total_warnings += warnings
            page_refs[page_id] = ru_ir_ref

        ctx.logger.info(
            "Translated %d pages (%d validation warnings)", pages_translated, total_warnings
        )
        return TranslationResult(
            document_id=ctx.document_id,
            pages_translated=pages_translated,
            validation_warnings=total_warnings,
            page_refs=page_refs,
        )

    def _process_page(
        self,
        ctx: StageContext,
        en_ir: PageIRV1,
        page_id: str,
        translator: TranslatorAdapter,
        concept_reg: ConceptRegistryV1 | None,
    ) -> tuple[int, str]:
        """Resume-aware per-page driver (S5U-1228).

        If a valid resume record exists for this page (EN IR unchanged, RU IR
        still on disk), skip the LLM call and reuse the cached translation —
        this is what lets a retry resume from the first incomplete page rather
        than re-translating completed ones. Otherwise translate, then persist
        the resume record after the RU IR is durably written.

        Returns ``(warning_count, ru_ir_relative_path)`` for
        ``TranslationResult.page_refs`` (S5U-1227), identical on the resumed and
        freshly-translated paths.
        """
        en_hash = en_ir_content_hash(en_ir)
        cached = load_resume_state(ctx, page_id, expected_en_hash=en_hash)
        if cached is not None:
            ctx.logger.info("Resumed %s from cache (skipping LLM)", page_id)
            return cached.warning_count, cached.ru_ir_ref

        warnings, ru_ir_ref = self._translate_page(ctx, en_ir, page_id, translator, concept_reg)
        persist_resume_state(
            ctx,
            page_id=page_id,
            en_ir_hash=en_hash,
            ru_ir_ref=ru_ir_ref,
            warning_count=warnings,
        )
        return warnings, ru_ir_ref.relative_path

    def _translate_page(
        self,
        ctx: StageContext,
        en_ir: PageIRV1,
        page_id: str,
        translator: TranslatorAdapter,
        concept_reg: ConceptRegistryV1 | None,
    ) -> tuple[int, ArtifactRef]:
        """Translate a single page and store the RU IR.

        Returns ``(warning_count, ru_ir_ref)`` — the content-addressed
        ``page_ir.v1.ru`` ref (its ``relative_path`` feeds
        ``TranslationResult.page_refs``; the ref also threads into the resume
        record so a resumed run can rebuild ``page_refs`` without re-translating).
        """
        ctx.logger.info("Translating %s", page_id)

        batch = build_translation_batch(
            en_ir,
            concept_registry=concept_reg,
            prompt_profile=ctx.config.translation.prompt_profile,
        )

        # Hardness routing (S5U-1541): only when explicitly enabled in config.
        # When disabled, model_profile="", meta shape, and chosen model are
        # byte-identical to pre-S5U-1541 (regression invariant).
        tcfg = ctx.config.translation
        model_profile = tcfg.model_default
        hardness_meta: dict[str, object] | None = None
        if tcfg.hardness.enabled:
            hres = compute_hardness(batch, tcfg.hardness, tcfg.model_default, tcfg.model_hard)
            model_profile = hres.chosen_model
            hardness_meta = hres.to_meta_dict()

        response = translator.translate_batch(batch, model_profile=model_profile)
        result = response.result
        expanded_batch = _expand_grouped_translation_batch(batch)
        expanded_result = _expand_grouped_translation_result(batch, result)

        # Persist translation metadata for auditability
        meta_data: dict[str, object] = {
            "batch_id": batch.batch_id,
            "page_id": page_id,
            "prompt_profile": batch.prompt_profile,
            "provider": response.meta.provider,
            "model": response.meta.model,
            "input_tokens": response.meta.input_tokens,
            "output_tokens": response.meta.output_tokens,
            "raw_response": response.meta.raw_response,
            "source_checksums": {s.segment_id: s.source_checksum for s in batch.segments},
            "fallback_used": response.meta.extra.get("fallback_used", False),
            "attempts": response.meta.extra.get("attempts", 1),
            # S5U-1226 — persist the primary provider's pre-fallback error so a
            # silent provider fallback is diagnosable from the run. Set by
            # FallbackTranslator only on the fallback path; ``None`` otherwise.
            "primary_error": response.meta.extra.get("primary_error"),
        }
        if hardness_meta is not None:
            meta_data["hardness"] = hardness_meta
            meta_data["hardness_chosen_model"] = model_profile
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="translation_meta.v1",
            scope="page",
            entity_id=page_id,
            data=meta_data,
        )

        qa_records = validate_translation(
            batch,
            result,
            concept_registry=concept_reg,
            document_id=ctx.document_id,
            page_id=page_id,
        )
        for record in qa_records:
            ctx.logger.warning(
                "Translation QA %s [%s]: %s",
                record.severity.value,
                record.code,
                record.message,
            )

        record_set = TranslationQARecordSetV1(
            document_id=ctx.document_id,
            page_id=page_id,
            records=qa_records,
        )
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="translation_qa_record_set.v1",
            scope="page",
            entity_id=page_id,
            data=record_set,
        )

        ru_blocks = rematerialize_ru_blocks(en_ir, expanded_batch, expanded_result)

        ru_ir = PageIRV1(
            document_id=ctx.document_id,
            page_id=page_id,
            page_number=en_ir.page_number,
            language=LanguageCode.RU,
            dimensions_pt=en_ir.dimensions_pt,
            blocks=ru_blocks,
            reading_order=en_ir.reading_order,
        )

        ru_ref = ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="page_ir.v1.ru",
            scope="page",
            entity_id=page_id,
            data=ru_ir,
        )
        return len(qa_records), ru_ref

    @staticmethod
    def _resolve_page_ids(ctx: StageContext) -> list[str]:
        """Get page IDs from EN IR artifacts in the store."""
        ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
        if ir_dir.exists():
            return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())

        msg = "No EN IR pages found. Run structure stage first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_en_ir(ctx: StageContext, page_id: str) -> PageIRV1 | None:
        """Load an EN PageIRV1 from the artifact store."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="page_ir.v1.en",
            scope="page",
            entity_id=page_id,
        )
        return PageIRV1.model_validate(data) if data else None

    @staticmethod
    def _load_concept_registry(ctx: StageContext) -> ConceptRegistryV1 | None:
        """Load the concept registry if configured."""
        glossary_path = ctx.config.repo_root / "configs" / "glossary" / "concepts.toml"
        if glossary_path.exists():
            return load_concept_registry(glossary_path)
        return None

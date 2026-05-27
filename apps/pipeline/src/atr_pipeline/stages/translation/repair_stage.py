"""Targeted post-critic Russian paragraph style repair stage."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_pipeline.services.llm.russian_style_repair import create_russian_style_repair
from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.translation.repair_helpers import (
    RepairStageContext,
    apply_repairs,
    build_repair_request,
    build_report,
    empty_response,
    style_qa_count,
    validated_repairs,
    write_translation_qa,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticPageV1


class TranslationStyleRepairResult(BaseModel):
    """Summary of targeted style repair execution."""

    document_id: str
    pages_seen: int = Field(ge=0)
    pages_repaired: int = Field(ge=0)
    paragraphs_repaired: int = Field(ge=0)


class TranslationStyleRepairStage:
    """Repair only paragraphs with style critic findings."""

    @property
    def name(self) -> str:
        return "translation_style_repair"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(
        self,
        ctx: RepairStageContext,
        input_data: BaseModel | None,
    ) -> TranslationStyleRepairResult:
        if not ctx.config.translation.style_repair_enabled:
            return TranslationStyleRepairResult(
                document_id=ctx.document_id,
                pages_seen=0,
                pages_repaired=0,
                paragraphs_repaired=0,
            )

        repair = create_russian_style_repair(ctx.config.translation)
        concept_reg = self._load_concept_registry(ctx)
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))
        pages_repaired = 0
        paragraphs_repaired = 0

        for page_id in page_ids:
            en_ir = self._load_page_ir(ctx, "page_ir.v1.en", page_id)
            ru_ir = self._load_page_ir(ctx, "page_ir.v1.ru", page_id)
            critic_page = self._load_critic_page(ctx, page_id)
            if ru_ir is None:
                ctx.logger.warning("Skipping repair for %s: missing RU IR", page_id)
                continue
            if en_ir is None:
                ctx.logger.warning("Repairing %s without EN source context", page_id)
            if critic_page is None:
                ctx.logger.warning("Skipping repair for %s: missing critic findings", page_id)
                continue

            request = build_repair_request(ctx.document_id, page_id, ru_ir, en_ir, critic_page)
            draft = (
                repair.repair_page(request).result
                if request.paragraphs
                else empty_response(ctx, page_id)
            )
            repairs = validated_repairs(request, draft)
            repaired_ir, changes = apply_repairs(ru_ir, request, repairs)
            if changes:
                self._write_ru_ir(ctx, repaired_ir, page_id)

            qa_count = write_translation_qa(
                ctx,
                en_ir=en_ir,
                ru_ir=repaired_ir,
                page_id=page_id,
                concept_reg=concept_reg,
            )
            report = build_report(
                ctx.document_id,
                page_id,
                critic_page,
                request,
                changes,
                qa_count,
                style_qa_count(repaired_ir),
            )
            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="translation_style_repair.v1",
                scope="page",
                entity_id=page_id,
                data=report,
            )
            if changes:
                pages_repaired += 1
                paragraphs_repaired += len(changes)

        ctx.logger.info(
            "Russian style repair completed for %d pages (%d repaired paragraphs)",
            pages_repaired,
            paragraphs_repaired,
        )
        return TranslationStyleRepairResult(
            document_id=ctx.document_id,
            pages_seen=len(page_ids),
            pages_repaired=pages_repaired,
            paragraphs_repaired=paragraphs_repaired,
        )

    @staticmethod
    def _resolve_page_ids(ctx: RepairStageContext) -> list[str]:
        ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.ru" / "page"
        if ir_dir.exists():
            return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())
        msg = "No RU IR pages found. Run translation stage first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_page_ir(
        ctx: RepairStageContext,
        schema_family: str,
        page_id: str,
    ) -> PageIRV1 | None:
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=schema_family,
            scope="page",
            entity_id=page_id,
        )
        return PageIRV1.model_validate(data) if data else None

    @staticmethod
    def _load_critic_page(
        ctx: RepairStageContext,
        page_id: str,
    ) -> TranslationStyleCriticPageV1 | None:
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="translation_style_critic.v1",
            scope="page",
            entity_id=page_id,
        )
        return TranslationStyleCriticPageV1.model_validate(data) if data else None

    @staticmethod
    def _load_concept_registry(ctx: RepairStageContext) -> ConceptRegistryV1 | None:
        glossary_path = ctx.config.repo_root / "configs" / "glossary" / "concepts.toml"
        if glossary_path.exists():
            return load_concept_registry(glossary_path)
        return None

    @staticmethod
    def _write_ru_ir(ctx: RepairStageContext, ru_ir: PageIRV1, page_id: str) -> None:
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="page_ir.v1.ru",
            scope="page",
            entity_id=page_id,
            data=ru_ir,
        )

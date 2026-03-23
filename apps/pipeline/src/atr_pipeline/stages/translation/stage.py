"""Translation stage — translate EN IR pages to RU using an LLM adapter."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_pipeline.services.llm.factory import create_translator
from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import validate_translation
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.enums import LanguageCode, StageScope
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
)

_BLOCK_TYPE_MAP: dict[str, type[BaseModel]] = {
    "heading": HeadingBlock,
    "paragraph": ParagraphBlock,
    "list": ListBlock,
    "list_item": ListItemBlock,
    "table": TableBlock,
    "callout": CalloutBlock,
    "figure": FigureBlock,
    "caption": CaptionBlock,
}

# Structural metadata fields to copy from source block (beyond block_id + children).
_STRUCTURAL_FIELDS: dict[str, list[str]] = {
    "heading": ["level"],
    "list": ["ordered"],
    "callout": ["variant"],
    "figure": ["asset_id"],
}


class TranslationResult(BaseModel):
    """Summary of translation across all pages."""

    document_id: str
    pages_translated: int = Field(ge=0)
    validation_warnings: int = Field(ge=0)


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
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> TranslationResult:
        concept_reg = self._load_concept_registry(ctx)
        translator = create_translator(ctx.config.translation, concept_registry=concept_reg)
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))

        pages_translated = 0
        total_warnings = 0

        for page_id in page_ids:
            en_ir = self._load_en_ir(ctx, page_id)
            if en_ir is None:
                ctx.logger.warning("Skipping %s: missing EN IR", page_id)
                continue

            warnings = self._translate_page(
                ctx,
                en_ir,
                page_id,
                translator,
                concept_reg,
            )
            pages_translated += 1
            total_warnings += warnings

        ctx.logger.info(
            "Translated %d pages (%d validation warnings)",
            pages_translated,
            total_warnings,
        )
        return TranslationResult(
            document_id=ctx.document_id,
            pages_translated=pages_translated,
            validation_warnings=total_warnings,
        )

    def _translate_page(
        self,
        ctx: StageContext,
        en_ir: PageIRV1,
        page_id: str,
        translator: TranslatorAdapter,
        concept_reg: ConceptRegistryV1 | None,
    ) -> int:
        """Translate a single page and store the RU IR. Returns warning count."""
        ctx.logger.info("Translating %s", page_id)

        batch = build_translation_batch(
            en_ir,
            concept_registry=concept_reg,
            prompt_profile=ctx.config.translation.prompt_profile,
        )
        response = translator.translate_batch(batch)
        result = response.result

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
        }
        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="translation_meta.v1",
            scope="page",
            entity_id=page_id,
            data=meta_data,
        )

        errors = validate_translation(batch, result, concept_registry=concept_reg)
        for e in errors:
            ctx.logger.warning("Validation: %s", e)

        ru_blocks: list[Block] = []
        for seg in result.segments:
            src_block = next(
                (b for b in en_ir.blocks if b.block_id == seg.segment_id),
                None,
            )
            if src_block is None:
                ctx.logger.warning(
                    "Segment %s has no matching source block, skipping",
                    seg.segment_id,
                )
                continue

            block_cls = _BLOCK_TYPE_MAP.get(src_block.type, ParagraphBlock)
            kwargs: dict[str, object] = {
                "block_id": seg.segment_id,
                "children": list(seg.target_inline),
            }
            for field in _STRUCTURAL_FIELDS.get(src_block.type, []):
                kwargs[field] = getattr(src_block, field)
            ru_blocks.append(cast(Block, block_cls(**kwargs)))

        ru_ir = PageIRV1(
            document_id=ctx.document_id,
            page_id=page_id,
            page_number=en_ir.page_number,
            language=LanguageCode.RU,
            dimensions_pt=en_ir.dimensions_pt,
            blocks=ru_blocks,
            reading_order=en_ir.reading_order,
        )

        ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="page_ir.v1.ru",
            scope="page",
            entity_id=page_id,
            data=ru_ir,
        )
        return len(errors)

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

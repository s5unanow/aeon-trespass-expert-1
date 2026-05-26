"""Translation stage — translate EN IR pages to RU using an LLM adapter."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.llm.base import TranslatorAdapter
from atr_pipeline.services.llm.factory import create_translator
from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.translation.grouping import (
    expand_grouped_batch,
    expand_grouped_result,
)
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
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    TableChild,
    TableRowBlock,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment
from atr_schemas.translation_qa_record_set_v1 import TranslationQARecordSetV1
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1

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


def _translated_by_id(result: TranslationResultV1) -> dict[str, TranslatedSegment]:
    """Index translated segments by their ``segment_id``."""
    return {seg.segment_id: seg for seg in result.segments}


def _batch_seg_by_id(batch: TranslationBatchV1) -> dict[str, TranslationSegment]:
    """Index batch segments by their ``segment_id``."""
    return {seg.segment_id: seg for seg in batch.segments}


def _expand_grouped_translation_batch(batch: TranslationBatchV1) -> TranslationBatchV1:
    """Return a block-addressable batch for validation/rematerialization."""
    return expand_grouped_batch(batch)


def _expand_grouped_translation_result(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> TranslationResultV1:
    """Return a block-addressable result by splitting narrative-group outputs."""
    return expand_grouped_result(batch, result)


def _rebuild_structured_table(
    src_block: TableBlock,
    *,
    batch_by_id: dict[str, TranslationSegment],
    translated_by_id: dict[str, TranslatedSegment],
) -> TableBlock:
    """S5U-734 — reassemble a structured RU ``TableBlock`` from per-cell segments.

    Preserves the EN row/cell structure (block ids, header flags, row ordering).
    Missing translations leave the cell structurally present with empty
    ``children`` rather than collapsing the row.
    """
    new_rows: list[TableChild] = []
    for row in src_block.children:
        if not isinstance(row, TableRowBlock):
            # Legacy mixed-content child; pass through unchanged. The
            # planner skipped these, so there is no translation to apply.
            new_rows.append(row)
            continue
        new_cells: list[TableCellBlock] = []
        for cell in row.cells:
            translated = translated_by_id.get(cell.block_id)
            target_inline: list[InlineNode] = (
                list(translated.target_inline) if translated is not None else []
            )
            new_cells.append(
                TableCellBlock(
                    block_id=cell.block_id,
                    bbox=cell.bbox,
                    header=cell.header,
                    children=target_inline,
                    translatable=cell.translatable,
                    source_ref=cell.source_ref,
                )
            )
        new_rows.append(
            TableRowBlock(
                block_id=row.block_id,
                bbox=row.bbox,
                header=row.header,
                cells=new_cells,
                translatable=row.translatable,
                source_ref=row.source_ref,
            )
        )
    # Silence unused-variable warnings from the batch index — the source of
    # truth for structure is the EN source block; the batch mapping is
    # retained for future use (e.g., untranslatable-cell policy).
    _ = batch_by_id
    return TableBlock(
        block_id=src_block.block_id,
        bbox=src_block.bbox,
        children=new_rows,
        translatable=src_block.translatable,
        source_ref=src_block.source_ref,
    )


def _rematerialize_ru_blocks(
    en_ir: PageIRV1,
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> list[Block]:
    """Rebuild the RU ``PageIRV1.blocks`` from the EN source IR and the
    translation result. Structured tables are reassembled per S5U-734; other
    blocks retain their prior single-segment re-materialization path.
    """
    translated_by_id = _translated_by_id(result)
    batch_by_id = _batch_seg_by_id(batch)

    ru_blocks: list[Block] = []
    for src_block in en_ir.blocks:
        # Structured TableBlock — per-cell re-assembly.
        if isinstance(src_block, TableBlock) and any(
            isinstance(c, TableRowBlock) for c in src_block.children
        ):
            ru_blocks.append(
                _rebuild_structured_table(
                    src_block,
                    batch_by_id=batch_by_id,
                    translated_by_id=translated_by_id,
                )
            )
            continue

        # Non-table or legacy flat table — use the top-level segment.
        translated = translated_by_id.get(src_block.block_id)
        if translated is None:
            continue

        block_cls = _BLOCK_TYPE_MAP.get(src_block.type, ParagraphBlock)
        kwargs: dict[str, object] = {
            "block_id": src_block.block_id,
            "children": list(translated.target_inline),
            "bbox": src_block.bbox,
        }
        for field in _STRUCTURAL_FIELDS.get(src_block.type, []):
            kwargs[field] = getattr(src_block, field)
        ru_blocks.append(cast(Block, block_cls(**kwargs)))

    return ru_blocks


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
        # split-back rematerialization. Bumped from 1.1 so cached per-block
        # translations re-execute.
        return "1.2"

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
        }
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

        ru_blocks = _rematerialize_ru_blocks(en_ir, expanded_batch, expanded_result)

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
        return len(qa_records)

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

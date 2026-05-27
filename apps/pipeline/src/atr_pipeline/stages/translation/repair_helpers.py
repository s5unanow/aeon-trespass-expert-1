"""Helpers for targeted Russian paragraph style repair."""

from __future__ import annotations

import difflib
import importlib
import sys
from collections import defaultdict
from collections.abc import Callable
from logging import Logger
from pathlib import Path
from typing import Any, Protocol, cast

from atr_pipeline.config.models import DocumentBuildConfig
from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageDraft,
    RepairPageRequest,
    repair_paragraph_from_critic,
)
from atr_pipeline.stages.translation.critic_stage import _block_text, _build_critic_request
from atr_pipeline.stages.translation.grouping import expand_grouped_batch
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_pipeline.stages.translation.validator import validate_translation
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    Block,
    InlineNode,
    PageIRV1,
    TableBlock,
    TableCellBlock,
    TableChild,
    TableRowBlock,
    TextInline,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_qa_record_set_v1 import TranslationQARecordSetV1
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1
from atr_schemas.translation_style_critic_v1 import (
    TranslationStyleCriticFindingV1,
    TranslationStyleCriticPageV1,
)
from atr_schemas.translation_style_repair_v1 import (
    TranslationStyleRepairChangeV1,
    TranslationStyleRepairPageV1,
)


class RepairStageContext(Protocol):
    """Subset of StageContext used by targeted style repair."""

    document_id: str
    config: DocumentBuildConfig
    artifact_store: ArtifactStore
    logger: Logger

    def filter_pages(self, page_ids: list[str]) -> list[str]: ...


def empty_response(ctx: RepairStageContext, page_id: str) -> RepairPageDraft:
    return RepairPageDraft(document_id=ctx.document_id, page_id=page_id, repairs=[])


def build_repair_request(
    document_id: str,
    page_id: str,
    ru_ir: PageIRV1,
    en_ir: PageIRV1 | None,
    critic_page: TranslationStyleCriticPageV1,
) -> RepairPageRequest:
    findings_by_id: dict[str, list[TranslationStyleCriticFindingV1]] = defaultdict(list)
    for finding in critic_page.findings:
        findings_by_id[finding.paragraph_id].append(finding)

    critic_request = _build_critic_request(document_id, page_id, ru_ir, en_ir)
    paragraphs = [
        repair_paragraph_from_critic(paragraph, findings_by_id[paragraph.paragraph_id])
        for paragraph in critic_request.paragraphs
        if findings_by_id.get(paragraph.paragraph_id)
    ]
    return RepairPageRequest(
        document_id=document_id,
        page_id=page_id,
        paragraphs=paragraphs,
    )


def validated_repairs(request: RepairPageRequest, draft: RepairPageDraft) -> dict[str, str]:
    if draft.document_id != request.document_id or draft.page_id != request.page_id:
        msg = f"Style repair returned mismatched document/page: {draft.document_id}/{draft.page_id}"
        raise RuntimeError(msg)
    requested_ids = {paragraph.paragraph_id for paragraph in request.paragraphs}
    repairs: dict[str, str] = {}
    for repair in draft.repairs:
        if repair.paragraph_id not in requested_ids:
            msg = f"Style repair returned unrequested paragraph ID: {repair.paragraph_id}"
            raise RuntimeError(msg)
        repairs[repair.paragraph_id] = repair.repaired_text
    return repairs


def apply_repairs(
    ru_ir: PageIRV1,
    request: RepairPageRequest,
    repairs: dict[str, str],
) -> tuple[PageIRV1, list[TranslationStyleRepairChangeV1]]:
    request_by_id = {paragraph.paragraph_id: paragraph for paragraph in request.paragraphs}
    changes: list[TranslationStyleRepairChangeV1] = []
    new_blocks = [_repair_block(block, request_by_id, repairs, changes) for block in ru_ir.blocks]
    return ru_ir.model_copy(update={"blocks": new_blocks}), changes


def write_translation_qa(
    ctx: RepairStageContext,
    *,
    en_ir: PageIRV1 | None,
    ru_ir: PageIRV1,
    page_id: str,
    concept_reg: ConceptRegistryV1 | None,
) -> int:
    if en_ir is None:
        return 0
    batch = expand_grouped_batch(
        build_translation_batch(
            en_ir,
            concept_registry=concept_reg,
            prompt_profile=ctx.config.translation.prompt_profile,
        )
    )
    result = _translation_result_from_ru_ir(batch, ru_ir)
    records = validate_translation(
        batch,
        result,
        concept_registry=concept_reg,
        document_id=ctx.document_id,
        page_id=page_id,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family="translation_qa_record_set.v1",
        scope="page",
        entity_id=page_id,
        data=TranslationQARecordSetV1(
            document_id=ctx.document_id,
            page_id=page_id,
            records=records,
        ),
    )
    return len(records)


def style_qa_count(ru_ir: PageIRV1) -> int:
    finder = _style_flag_finder()
    return sum(len(finder(_block_text(block))) for block in ru_ir.blocks)


def _style_flag_finder() -> Callable[[str], list[Any]]:
    repo_root = Path(__file__).resolve().parents[6]
    repo_path = str(repo_root)
    added = repo_path not in sys.path
    if added:
        sys.path.insert(0, repo_path)
    try:
        qa_checks = importlib.import_module("scripts.translation_eval.qa_checks")
        return cast(
            "Callable[[str], list[Any]]",
            cast(Any, qa_checks).find_style_red_flags,
        )
    finally:
        if added:
            sys.path.remove(repo_path)


def build_report(
    document_id: str,
    page_id: str,
    critic_page: TranslationStyleCriticPageV1,
    request: RepairPageRequest,
    changes: list[TranslationStyleRepairChangeV1],
    qa_count: int,
    style_count: int,
) -> TranslationStyleRepairPageV1:
    changed_ids = {change.paragraph_id for change in changes}
    requested_ids = [paragraph.paragraph_id for paragraph in request.paragraphs]
    return TranslationStyleRepairPageV1(
        document_id=document_id,
        page_id=page_id,
        source_critic_findings_count=len(critic_page.findings),
        repaired_paragraph_ids=[pid for pid in requested_ids if pid in changed_ids],
        skipped_paragraph_ids=[pid for pid in requested_ids if pid not in changed_ids],
        changes=changes,
        post_repair_translation_qa_count=qa_count,
        post_repair_style_qa_count=style_count,
    )


def _repair_block(
    block: Block,
    request_by_id: dict[str, Any],
    repairs: dict[str, str],
    changes: list[TranslationStyleRepairChangeV1],
) -> Block:
    if isinstance(block, TableBlock):
        return _repair_table(block, request_by_id, repairs, changes)
    block_id = getattr(block, "block_id", "")
    children = getattr(block, "children", None)
    if block_id not in repairs or not isinstance(children, list):
        return block
    return block.model_copy(
        update={
            "children": _repair_inlines(
                block_id,
                block.type,
                children,
                request_by_id,
                repairs,
                changes,
            )
        }
    )


def _repair_table(
    block: TableBlock,
    request_by_id: dict[str, Any],
    repairs: dict[str, str],
    changes: list[TranslationStyleRepairChangeV1],
) -> TableBlock:
    new_children: list[TableChild] = []
    for child in block.children:
        if not isinstance(child, TableRowBlock):
            new_children.append(child)
            continue
        cells = [_repair_cell(cell, request_by_id, repairs, changes) for cell in child.cells]
        new_children.append(child.model_copy(update={"cells": cells}))
    return block.model_copy(update={"children": new_children})


def _repair_cell(
    cell: TableCellBlock,
    request_by_id: dict[str, Any],
    repairs: dict[str, str],
    changes: list[TranslationStyleRepairChangeV1],
) -> TableCellBlock:
    if cell.block_id not in repairs:
        return cell
    children = _repair_inlines(
        cell.block_id,
        cell.type,
        cell.children,
        request_by_id,
        repairs,
        changes,
    )
    return cell.model_copy(update={"children": children})


def _repair_inlines(
    paragraph_id: str,
    block_type: str,
    children: list[InlineNode],
    request_by_id: dict[str, Any],
    repairs: dict[str, str],
    changes: list[TranslationStyleRepairChangeV1],
) -> list[InlineNode]:
    before = request_by_id[paragraph_id].current_text
    after = repairs[paragraph_id]
    if after == before:
        return children
    findings = request_by_id[paragraph_id].findings
    changes.append(
        TranslationStyleRepairChangeV1(
            paragraph_id=paragraph_id,
            block_type=block_type,
            before_text=before,
            after_text=after,
            finding_quotes=[finding.quote for finding in findings],
            diff=_unified_diff(before, after),
        )
    )
    return _replace_text_preserving_non_text(children, after)


def _replace_text_preserving_non_text(children: list[InlineNode], text: str) -> list[InlineNode]:
    new_children: list[InlineNode] = []
    placed = False
    for node in children:
        if isinstance(node, TextInline):
            if not placed:
                new_children.append(
                    node.model_copy(update={"text": text, "lang": node.lang or LanguageCode.RU})
                )
                placed = True
            continue
        new_children.append(node)
    if not placed:
        new_children.insert(0, TextInline(text=text, lang=LanguageCode.RU))
    return new_children


def _unified_diff(before: str, after: str) -> list[str]:
    return list(
        difflib.unified_diff(
            [before],
            [after],
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


def _translation_result_from_ru_ir(
    batch: TranslationBatchV1,
    ru_ir: PageIRV1,
) -> TranslationResultV1:
    inline_by_id = _inline_nodes_by_id(ru_ir)
    return TranslationResultV1(
        batch_id=batch.batch_id,
        segments=[
            TranslatedSegment(
                segment_id=segment.segment_id,
                target_inline=list(inline_by_id.get(segment.segment_id, [])),
            )
            for segment in batch.segments
        ],
    )


def _inline_nodes_by_id(page_ir: PageIRV1) -> dict[str, list[InlineNode]]:
    result: dict[str, list[InlineNode]] = {}
    for block in page_ir.blocks:
        if isinstance(block, TableBlock):
            for child in block.children:
                if isinstance(child, TableRowBlock):
                    for cell in child.cells:
                        result[cell.block_id] = list(cell.children)
            continue
        children = getattr(block, "children", None)
        if isinstance(children, list):
            result[getattr(block, "block_id", "")] = list(children)
    return result

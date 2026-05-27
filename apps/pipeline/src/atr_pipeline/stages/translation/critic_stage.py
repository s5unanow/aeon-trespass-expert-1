"""Post-translation Russian monolingual style critic stage."""

from __future__ import annotations

import re
from logging import Logger
from typing import NamedTuple, Protocol

from pydantic import BaseModel, Field

from atr_pipeline.config.models import DocumentBuildConfig
from atr_pipeline.services.llm.russian_style_critic import (
    CriticPageRequest,
    CriticParagraph,
    create_russian_style_critic,
)
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import (
    Block,
    HeadingBlock,
    InlineNode,
    PageIRV1,
    TableBlock,
    TableRowBlock,
    TextInline,
)


class _StageContextLike(Protocol):
    """Subset of StageContext used by this stage."""

    document_id: str
    config: DocumentBuildConfig
    artifact_store: ArtifactStore
    logger: Logger

    def filter_pages(self, page_ids: list[str]) -> list[str]: ...


class TranslationStyleCriticResult(BaseModel):
    """Summary of Russian style critic execution."""

    document_id: str
    pages_critiqued: int = Field(ge=0)
    findings_count: int = Field(ge=0)


class _ParagraphDraft(NamedTuple):
    paragraph_id: str
    block_type: str
    ru_text: str
    source_text: str
    prev_heading: str


class TranslationStyleCriticStage:
    """Critique Russian translation drafts without rewriting them."""

    @property
    def name(self) -> str:
        return "translation_style_critic"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(
        self,
        ctx: _StageContextLike,
        input_data: BaseModel | None,
    ) -> TranslationStyleCriticResult:
        if not ctx.config.translation.style_critic_enabled:
            return TranslationStyleCriticResult(
                document_id=ctx.document_id,
                pages_critiqued=0,
                findings_count=0,
            )

        critic = create_russian_style_critic(ctx.config.translation)
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))
        pages_critiqued = 0
        findings_count = 0

        for page_id in page_ids:
            ru_ir = self._load_page_ir(ctx, "page_ir.v1.ru", page_id)
            en_ir = self._load_page_ir(ctx, "page_ir.v1.en", page_id)
            if ru_ir is None:
                ctx.logger.warning("Skipping %s: missing RU IR", page_id)
                continue
            if en_ir is None:
                ctx.logger.warning("Critiquing %s without EN source context", page_id)
            request = _build_critic_request(ctx.document_id, page_id, ru_ir, en_ir)
            response = critic.critique_page(request)
            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="translation_style_critic.v1",
                scope="page",
                entity_id=page_id,
                data=response.result,
            )
            pages_critiqued += 1
            findings_count += len(response.result.findings)

        ctx.logger.info(
            "Russian style critic completed for %d pages (%d findings)",
            pages_critiqued,
            findings_count,
        )
        return TranslationStyleCriticResult(
            document_id=ctx.document_id,
            pages_critiqued=pages_critiqued,
            findings_count=findings_count,
        )

    @staticmethod
    def _resolve_page_ids(ctx: _StageContextLike) -> list[str]:
        ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.ru" / "page"
        if ir_dir.exists():
            return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())
        msg = "No RU IR pages found. Run translation stage first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_page_ir(
        ctx: _StageContextLike,
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


def _build_critic_request(
    document_id: str,
    page_id: str,
    ru_ir: PageIRV1,
    en_ir: PageIRV1 | None,
) -> CriticPageRequest:
    source_text_by_id = _text_by_id(en_ir) if en_ir is not None else {}
    drafts = _collect_ru_drafts(ru_ir, source_text_by_id)
    paragraphs: list[CriticParagraph] = []
    for index, draft in enumerate(drafts):
        prev_text = drafts[index - 1].ru_text if index > 0 else ""
        next_text = drafts[index + 1].ru_text if index + 1 < len(drafts) else ""
        paragraphs.append(
            CriticParagraph(
                paragraph_id=draft.paragraph_id,
                block_type=draft.block_type,
                ru_text=draft.ru_text,
                source_text=draft.source_text,
                prev_ru_text=prev_text,
                next_ru_text=next_text,
                prev_heading=draft.prev_heading,
            )
        )
    return CriticPageRequest(
        document_id=document_id,
        page_id=page_id,
        paragraphs=paragraphs,
    )


def _collect_ru_drafts(
    ru_ir: PageIRV1,
    source_text_by_id: dict[str, str],
) -> list[_ParagraphDraft]:
    drafts: list[_ParagraphDraft] = []
    prev_heading = ""

    for block in ru_ir.blocks:
        block_type = getattr(block, "type", "")
        if isinstance(block, TableBlock) and any(
            isinstance(child, TableRowBlock) for child in block.children
        ):
            for row in block.children:
                if not isinstance(row, TableRowBlock):
                    continue
                for cell in row.cells:
                    text = _inline_text(list(cell.children))
                    if text:
                        drafts.append(
                            _ParagraphDraft(
                                cell.block_id,
                                cell.type,
                                text,
                                source_text_by_id.get(cell.block_id, ""),
                                prev_heading,
                            )
                        )
            continue

        text = _block_text(block)
        if text:
            drafts.append(
                _ParagraphDraft(
                    getattr(block, "block_id", ""),
                    block_type,
                    text,
                    source_text_by_id.get(getattr(block, "block_id", ""), ""),
                    prev_heading,
                )
            )
        if isinstance(block, HeadingBlock) and text:
            prev_heading = text

    return drafts


def _text_by_id(page_ir: PageIRV1) -> dict[str, str]:
    result: dict[str, str] = {}
    for block in page_ir.blocks:
        if isinstance(block, TableBlock) and any(
            isinstance(child, TableRowBlock) for child in block.children
        ):
            for row in block.children:
                if not isinstance(row, TableRowBlock):
                    continue
                for cell in row.cells:
                    text = _inline_text(list(cell.children))
                    if text:
                        result[cell.block_id] = text
            continue
        text = _block_text(block)
        if text:
            result[getattr(block, "block_id", "")] = text
    return result


def _block_text(block: Block) -> str:
    children = getattr(block, "children", [])
    if not isinstance(children, list):
        return ""
    return _inline_text(children)


def _inline_text(nodes: list[InlineNode]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, TextInline):
            parts.append(node.text)
        else:
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()

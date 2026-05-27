# ruff: noqa: RUF001  — Cyrillic prompt text and examples are intentional.
"""Targeted Russian paragraph style repair adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.services.llm.russian_style_critic import CriticParagraph
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticFindingV1

_SYSTEM_PROMPT = """\
You are a Russian literary line editor for a board-game rulebook.
Repair only the paragraphs listed in the payload. Do not rewrite the page.

For each paragraph, use the English source only as local context. Preserve
structure, mechanics, numeric references, bracket placeholders, glossary terms,
and every fact already present in the Russian draft. Apply the critic findings
as local prose repairs only. Return JSON with one replacement string per
paragraph_id.
"""


class RepairParagraph(BaseModel):
    """One paragraph selected for targeted repair."""

    model_config = ConfigDict(extra="forbid")

    paragraph_id: str = Field(min_length=1)
    block_type: str = ""
    current_text: str
    source_text: str = ""
    prev_ru_text: str = ""
    next_ru_text: str = ""
    prev_heading: str = ""
    findings: list[TranslationStyleCriticFindingV1] = Field(default_factory=list)


class RepairPageRequest(BaseModel):
    """Repair request for one translated page."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    page_id: str
    paragraphs: list[RepairParagraph] = Field(default_factory=list)


class RepairedParagraph(BaseModel):
    """Replacement text for one requested paragraph."""

    model_config = ConfigDict(extra="forbid")

    paragraph_id: str = Field(min_length=1)
    repaired_text: str = Field(min_length=1)


class RepairPageDraft(BaseModel):
    """Validated repair adapter output."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    page_id: str
    repairs: list[RepairedParagraph] = Field(default_factory=list)


@dataclass
class RussianStyleRepairMeta:
    """Audit metadata captured from a style-repair call."""

    provider: str = ""
    model: str = ""
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class RussianStyleRepairResponse:
    """Validated repair output plus call metadata."""

    result: RepairPageDraft
    meta: RussianStyleRepairMeta


@runtime_checkable
class RussianStyleRepairAdapter(Protocol):
    """Protocol implemented by Russian style repair adapters."""

    def repair_page(self, request: RepairPageRequest) -> RussianStyleRepairResponse: ...


_MOCK_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("с великим трепетом", "с благоговейным трепетом"),
    ("обошло древний мегаполис", "обошло древний город"),
    ("убожество великолепия", "жалкое великолепие"),
)


class MockRussianStyleRepair:
    """Deterministic targeted repair adapter for fixtures and unit tests."""

    def repair_page(self, request: RepairPageRequest) -> RussianStyleRepairResponse:
        repairs: list[RepairedParagraph] = []
        for paragraph in request.paragraphs:
            text = paragraph.current_text
            for before, after in _MOCK_REPLACEMENTS:
                text = text.replace(before, after)
            repairs.append(
                RepairedParagraph(
                    paragraph_id=paragraph.paragraph_id,
                    repaired_text=text,
                )
            )
        result = RepairPageDraft(
            document_id=request.document_id,
            page_id=request.page_id,
            repairs=repairs,
        )
        return RussianStyleRepairResponse(
            result=result,
            meta=RussianStyleRepairMeta(
                provider="mock",
                model="mock-style-repair-v1",
                raw_response=result.model_dump_json(),
            ),
        )


def build_repair_prompt(request: RepairPageRequest) -> str:
    """Build the prompt sent to the Codex repair adapter."""
    schema = RepairPageDraft.model_json_schema()
    payload = request.model_dump(mode="json")
    return "\n\n".join(
        [
            _SYSTEM_PROMPT,
            "You MUST respond with valid JSON matching this schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "Repair this page payload:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def repair_paragraph_from_critic(
    paragraph: CriticParagraph,
    findings: list[TranslationStyleCriticFindingV1],
) -> RepairParagraph:
    """Convert critic context into a repair request paragraph."""
    return RepairParagraph(
        paragraph_id=paragraph.paragraph_id,
        block_type=paragraph.block_type,
        current_text=paragraph.ru_text,
        source_text=paragraph.source_text,
        prev_ru_text=paragraph.prev_ru_text,
        next_ru_text=paragraph.next_ru_text,
        prev_heading=paragraph.prev_heading,
        findings=findings,
    )


def create_russian_style_repair(
    config: TranslationConfig,
) -> RussianStyleRepairAdapter:
    """Instantiate the configured targeted style repair adapter."""
    provider = config.style_repair_provider or config.style_critic_provider or config.provider
    if provider == "mock":
        return MockRussianStyleRepair()
    if provider != "codex-cli":
        msg = f"Russian style repair supports only 'codex-cli' or 'mock', got {provider!r}."
        raise ValueError(msg)

    from atr_pipeline.services.llm.russian_style_repair_codex import CodexRussianStyleRepair

    cli_opts = config.provider_options.cli
    return CodexRussianStyleRepair(
        model=(
            config.style_repair_model
            or config.style_critic_model
            or config.model_hard
            or config.model_default
        ),
        timeout_seconds=cli_opts.timeout_seconds,
        reasoning_effort=config.style_repair_reasoning_effort or "high",
        sandbox=cli_opts.sandbox or "read-only",
        approval_policy=cli_opts.approval_policy or "never",
        executable=cli_opts.executable,
        json_events=cli_opts.json_mode,
    )

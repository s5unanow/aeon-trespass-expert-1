# ruff: noqa: RUF001  — Cyrillic prompt text and examples are intentional.
"""Russian monolingual style critic adapters for translated rulebook prose."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from atr_pipeline.config.models import TranslationConfig
from atr_schemas.enums import Severity
from atr_schemas.translation_style_critic_v1 import (
    TranslationStyleCriticFindingV1,
    TranslationStyleCriticPageV1,
)

_SYSTEM_PROMPT = """\
You are a monolingual Russian style critic for a board-game rulebook.
Read the Russian draft as Russian prose first. Use the short English source
only as local context for antecedents and scene function.

Return paragraph-local JSON findings only. Do not rewrite the page or propose
whole-paragraph replacements. Each finding must name the paragraph_id, severity,
an exact Russian quote from that paragraph, why it reads poorly, and one or more
local suggestions.

Look for awkward collocations, bad rhythm, repeated openers, stiff calques,
unclear antecedents, and context-inappropriate term choices. Mechanics and
terminology drift are out of scope unless the wording is also hard to read in
Russian. If the prose is acceptable, return an empty findings list.
"""


class CriticParagraph(BaseModel):
    """One Russian paragraph plus minimal source context for the critic."""

    model_config = ConfigDict(extra="forbid")

    paragraph_id: str = Field(min_length=1)
    block_type: str = ""
    ru_text: str = ""
    source_text: str = ""
    prev_ru_text: str = ""
    next_ru_text: str = ""
    prev_heading: str = ""


class CriticPageRequest(BaseModel):
    """Critic request for one translated page."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    page_id: str
    paragraphs: list[CriticParagraph] = Field(default_factory=list)


@dataclass
class RussianStyleCriticMeta:
    """Audit metadata captured from a style-critic call."""

    provider: str = ""
    model: str = ""
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class RussianStyleCriticResponse:
    """Validated critic output plus call metadata."""

    result: TranslationStyleCriticPageV1
    meta: RussianStyleCriticMeta


@runtime_checkable
class RussianStyleCriticAdapter(Protocol):
    """Protocol implemented by Russian style critic adapters."""

    def critique_page(self, request: CriticPageRequest) -> RussianStyleCriticResponse: ...


@dataclass(frozen=True)
class _KnownStyleRule:
    quote: str
    why: str
    suggestions: tuple[str, ...]
    severity: Severity = Severity.WARNING


_KNOWN_STYLE_RULES: Final[tuple[_KnownStyleRule, ...]] = (
    _KnownStyleRule(
        quote="с великим трепетом",
        why="Коллокация звучит тяжеловесно и книжно-механически.",
        suggestions=("Заменить на «с благоговейным трепетом» или перестроить фразу.",),
    ),
    _KnownStyleRule(
        quote="обошло древний мегаполис",
        why="«Мегаполис» выбивается из мифо-античного регистра и звучит современно.",
        suggestions=("Выбрать «древний город», «полис» или конкретное место сцены.",),
    ),
    _KnownStyleRule(
        quote="убожество великолепия",
        why="Калька сталкивает абстрактные существительные и сбивает образ.",
        suggestions=("Переформулировать как «жалкое великолепие» или точнее назвать контраст.",),
    ),
)


class MockRussianStyleCritic:
    """Deterministic style critic for fixtures and unit tests."""

    def critique_page(self, request: CriticPageRequest) -> RussianStyleCriticResponse:
        findings: list[TranslationStyleCriticFindingV1] = []
        for paragraph in request.paragraphs:
            findings.extend(_known_rule_findings(paragraph))
            repeated = _repeated_opener_finding(paragraph)
            if repeated is not None:
                findings.append(repeated)
            antecedent = _unclear_antecedent_finding(paragraph)
            if antecedent is not None:
                findings.append(antecedent)

        result = TranslationStyleCriticPageV1(
            document_id=request.document_id,
            page_id=request.page_id,
            findings=findings,
        )
        return RussianStyleCriticResponse(
            result=result,
            meta=RussianStyleCriticMeta(
                provider="mock",
                model="mock-style-critic-v1",
                raw_response=result.model_dump_json(),
            ),
        )


def _known_rule_findings(
    paragraph: CriticParagraph,
) -> list[TranslationStyleCriticFindingV1]:
    findings: list[TranslationStyleCriticFindingV1] = []
    for rule in _KNOWN_STYLE_RULES:
        if rule.quote not in paragraph.ru_text:
            continue
        findings.append(
            TranslationStyleCriticFindingV1(
                paragraph_id=paragraph.paragraph_id,
                severity=rule.severity,
                quote=rule.quote,
                why=rule.why,
                suggestions=list(rule.suggestions),
            )
        )
    return findings


def _repeated_opener_finding(
    paragraph: CriticParagraph,
) -> TranslationStyleCriticFindingV1 | None:
    starts = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph.ru_text)
        if sentence.strip()
    ]
    you_openers = sum(1 for sentence in starts if re.match(r"^Вы\b", sentence))
    if you_openers < 3:
        return None
    return TranslationStyleCriticFindingV1(
        paragraph_id=paragraph.paragraph_id,
        severity=Severity.INFO,
        quote="Вы",
        why="Несколько соседних фраз начинаются одинаково, из-за чего ритм становится рубленым.",
        suggestions=["Сдвинуть обстоятельство или объединить часть коротких фраз."],
    )


def _unclear_antecedent_finding(
    paragraph: CriticParagraph,
) -> TranslationStyleCriticFindingV1 | None:
    match = re.search(r"\bНо (?:только несколько|лишь немногие)\b", paragraph.ru_text)
    if match is None:
        return None
    return TranslationStyleCriticFindingV1(
        paragraph_id=paragraph.paragraph_id,
        severity=Severity.WARNING,
        quote=match.group(0),
        why="Фраза оставляет неясным, кто или что имеются в виду.",
        suggestions=["Назвать пропущенный предмет или группу внутри этой же фразы."],
    )


def build_critic_prompt(request: CriticPageRequest) -> str:
    """Build the prompt sent to the Codex style critic."""
    schema = TranslationStyleCriticPageV1.model_json_schema()
    payload = request.model_dump(mode="json")
    return "\n\n".join(
        [
            _SYSTEM_PROMPT,
            "You MUST respond with valid JSON matching this schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "Critique this page payload:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def create_russian_style_critic(
    config: TranslationConfig,
) -> RussianStyleCriticAdapter:
    """Instantiate the configured Russian style critic adapter."""
    provider = config.style_critic_provider or config.provider
    if provider == "mock":
        return MockRussianStyleCritic()
    if provider != "codex-cli":
        msg = f"Russian style critic supports only 'codex-cli' or 'mock', got {provider!r}."
        raise ValueError(msg)

    from atr_pipeline.services.llm.russian_style_critic_codex import (
        CodexRussianStyleCritic,
    )

    cli_opts = config.provider_options.cli
    return CodexRussianStyleCritic(
        model=config.style_critic_model or config.model_hard or config.model_default,
        timeout_seconds=cli_opts.timeout_seconds,
        reasoning_effort=config.style_critic_reasoning_effort or "high",
        sandbox=cli_opts.sandbox or "read-only",
        approval_policy=cli_opts.approval_policy or "never",
        executable=cli_opts.executable,
        json_events=cli_opts.json_mode,
    )

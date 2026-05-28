# ruff: noqa: RUF001  — Cyrillic regex ranges are intentional.
"""Russian prose style QA checks for local translation evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .qa_models import QAFinding

_SENTENCE_SPLIT_RE = re.compile(r"(?<!См\.)(?<=[.!?…])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_LEADING_PUNCT_RE = re.compile(r"^[\s\"'«»„“”()—–-]+")
_NAVIGATION_RE = re.compile(
    r"\b(?:Перейдите\s+к|См\.\s*0\d{3}|Смотрите\s+0\d{3}|"
    r"Отметьте\s+«?параграф|Запомните\s+«?параграф)\b",
    re.IGNORECASE,
)
_MECHANICS_RE = re.compile(
    r"\b(?:Дипломатия|Мудрость|Прозрение|Выживание|Минойцы|"
    r"Рогоприсягнувшие|Слава|Жизнь|Судьба|Урон)\b|[+-]\d|"
    r"\(\s*\d+\+\s*\)|\\(?:mathbf|boldsymbol)",
    re.IGNORECASE,
)
_MECHANICS_COMMAND_RE = re.compile(
    r"^\s*(?:Получите|Потеряйте|Вернитесь|Возвращайтесь|"
    r"Лидер\s+отряда\s+получает)\b",
    re.IGNORECASE,
)
_OUTCOME_LABEL_RE = re.compile(r"^\s*(?:Успех|Провал|Ничья|\d+\+:)\b", re.IGNORECASE)
_HARD_OPENERS = ("Вы", "И", "Но", "Затем", "Это", "Когда")
_YOU_VERB_SUFFIXES = (
    "аете",
    "яете",
    "ете",
    "ите",
    "ёте",
    "аетесь",
    "яетесь",
    "етесь",
    "итесь",
)
_STYLE_WINDOW = 6
_STYLE_CLUSTER_THRESHOLD = 4
_SHORT_SENTENCE_WORD_LIMIT = 4
_HARD_STOP_MIN_SENTENCES = 6
_HARD_STOP_RATIO_THRESHOLD = 0.60
_LANDING_PARTY_CONTEXT_RE = (
    r"(?:на\s+берег\w*[^.!?…]{0,80}\bвысадочн\w*\s+отряд\w*\b|"
    r"\bвысадочн\w*\s+отряд\w*\b[^.!?…]{0,80}"
    r"(?:на\s+берег|для\s+встреч|с\s+минойц|к\s+минойц|посл))"
)
_STYLE_RED_FLAGS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"Но\s+лишь\s+немногих", re.IGNORECASE),
        "Context error: 'few' refers to lamps/lights, not animate people.",
    ),
    (
        re.compile(r"на\s+страже\s+стоит\s+Стража", re.IGNORECASE),
        "Tautology: recast Horned Guard instead of 'guard stands on guard'.",
    ),
    (
        re.compile(r"Запомните\s+«параграф", re.IGNORECASE),
        "Gamebook convention: use 'Отметьте'/'Запишите' for Note passage.",
    ),
    (
        re.compile(r"(?m)^\s*См\.\s+0\d{3}\.?\s*$"),
        "Gamebook navigation: use 'Перейдите к NNNN' for standalone See refs.",
    ),
    (
        re.compile(r"Рогатого\s+Города"),
        "Generic noun should be lowercase in running prose: 'Рогатого города'.",
    ),
    (
        re.compile(r"\b(?:с|к|о|об|для|у|над|под|перед|между)\s+Минойц"),
        "Demonym should be lowercase in running Russian prose, but title/label "
        "forms may stay uppercase.",
    ),
    (
        re.compile(r"звук\w*\s+натягива\w+\s+тетив\w*", re.IGNORECASE),
        "Awkward collocation: prefer 'звук натягиваемой тетивы' or a stronger "
        "image such as 'треск натягиваемых тетив'.",
    ),
    (
        re.compile(_LANDING_PARTY_CONTEXT_RE, re.IGNORECASE),
        "Context check: 'высадочный отряд' is often too military/technical. "
        "Choose the Russian term by scene function: for shore contact prefer "
        "'передовой отряд' or 'отряд на берег'; for clue-search or scouting "
        "prefer 'поисковый отряд' or 'разведывательный отряд'.",
    ),
    (
        re.compile(r"\bимеет\s+значени[ея]\b", re.IGNORECASE),
        "Stiff register: 'имеет значение' usually calques 'matters'. Recast "
        "the emphasis as 'важна/важно/важен' or a concrete action.",
    ),
    (
        re.compile(
            r"\bобраща\w*\s+к\s+ним\b[^.!?…]*(?:словно|подобно)\s+жрец",
            re.IGNORECASE,
        ),
        "Generic speech verb: in public prophetic address prefer 'взывает к "
        "ним' or another scene-specific verb instead of flat 'обращается к ним'.",
    ),
    (
        re.compile(r"\bгруб\w*\s+пробуждени\w*\b", re.IGNORECASE),
        "Stiff register: 'грубое пробуждение' is a literal calque. Prefer "
        "'тяжелое пробуждение' or a concrete description of the ordeal.",
    ),
    (
        re.compile(r"\bметрополи\w*\b", re.IGNORECASE),
        "modern administrative register: 'метрополия' breaks mythic prose. "
        "Prefer 'город', 'оплот', or a concrete place noun that fits the scene.",
    ),
    (
        re.compile(r"\bускоря\w*\s+шаг\b", re.IGNORECASE),
        "Awkward movement collocation: prefer 'прибавляете шагу' or recast "
        "the sentence around the character's urgency.",
    ),
)


@dataclass(frozen=True)
class _StyleSentence:
    opener: str | None
    word_count: int
    is_you_verb: bool


def find_style_red_flags(ru: str) -> list[QAFinding]:
    """Return high-confidence prose failures learned from human review."""
    findings: list[QAFinding] = []
    for pattern, detail in _STYLE_RED_FLAGS:
        if pattern.search(ru):
            findings.append(QAFinding(code="style_red_flag", detail=detail))

    for paragraph in _style_paragraphs(ru):
        style_sentences = _style_sentences(paragraph)
        findings.extend(_find_repeated_openers(style_sentences))
        findings.extend(_find_you_verb_cadence(style_sentences))
        findings.extend(_find_short_sentence_clusters(style_sentences))
        findings.extend(_find_hard_stop_ratio(style_sentences))
    return findings


def _style_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _style_sentences(text: str) -> list[_StyleSentence]:
    sentences: list[_StyleSentence] = []
    for raw_sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = raw_sentence.strip()
        if not sentence or _is_mechanics_or_navigation_sentence(sentence):
            continue
        words = _WORD_RE.findall(sentence)
        sentences.append(
            _StyleSentence(
                opener=_sentence_opener(sentence),
                word_count=len(words),
                is_you_verb=_starts_with_you_verb(sentence),
            )
        )
    return sentences


def _sentence_opener(sentence: str) -> str | None:
    normalized = _LEADING_PUNCT_RE.sub("", sentence)
    match = _WORD_RE.match(normalized)
    if match is None:
        return None
    first_word = match.group(0).lower()
    for opener in _HARD_OPENERS:
        if first_word == opener.lower():
            return opener
    return None


def _starts_with_you_verb(sentence: str) -> bool:
    normalized = _LEADING_PUNCT_RE.sub("", sentence)
    match = re.match(r"(?i)^вы\s+(?:не\s+)?(?P<verb>[А-Яа-яЁё]+)\b", normalized)
    if match is None:
        return False
    return match.group("verb").lower().endswith(_YOU_VERB_SUFFIXES)


def _is_mechanics_or_navigation_sentence(sentence: str) -> bool:
    if _NAVIGATION_RE.search(sentence):
        return True
    if _OUTCOME_LABEL_RE.match(sentence) and len(_WORD_RE.findall(sentence)) <= 2:
        return True
    if ":" in sentence and _MECHANICS_RE.search(sentence):
        return True
    if _MECHANICS_RE.search(sentence) and re.search(r"[+-]\d|\(\s*\d+\+\s*\)|\\", sentence):
        return True
    return bool(_MECHANICS_COMMAND_RE.match(sentence) and _MECHANICS_RE.search(sentence))


def _find_repeated_openers(sentences: list[_StyleSentence]) -> list[QAFinding]:
    findings: list[QAFinding] = []
    for opener in _HARD_OPENERS:
        if _has_window_cluster([sentence.opener == opener for sentence in sentences]):
            findings.append(
                QAFinding(
                    code="style_red_flag",
                    detail=(
                        f"Cadence cluster: repeated opener '{opener}' appears at least "
                        f"{_STYLE_CLUSTER_THRESHOLD} times within {_STYLE_WINDOW} prose "
                        "sentences. Vary the rhythm by moving time/place first, merging "
                        "clauses, or choosing a concrete subject."
                    ),
                )
            )
    return findings


def _find_you_verb_cadence(sentences: list[_StyleSentence]) -> list[QAFinding]:
    if not _has_window_cluster([sentence.is_you_verb for sentence in sentences]):
        return []
    return [
        QAFinding(
            code="style_red_flag",
            detail=(
                "Cadence cluster: repeated 'Вы + verb' sentence starts make the "
                "Russian read translated. Recast one or more sentences with an "
                "initial circumstance, a concrete noun subject, or a combined clause."
            ),
        )
    ]


def _find_short_sentence_clusters(sentences: list[_StyleSentence]) -> list[QAFinding]:
    if not _has_window_cluster(_short_sentence_mask(sentences)):
        return []
    return [
        QAFinding(
            code="style_red_flag",
            detail=(
                "Cadence cluster: too many short prose sentences in one passage. "
                "Outside mechanics/navigation, combine beats or restore antecedents "
                "so the Russian paragraph has literary flow."
            ),
        )
    ]


def _find_hard_stop_ratio(sentences: list[_StyleSentence]) -> list[QAFinding]:
    if len(sentences) < _HARD_STOP_MIN_SENTENCES:
        return []
    short_count = sum(_short_sentence_mask(sentences))
    if short_count / len(sentences) < _HARD_STOP_RATIO_THRESHOLD:
        return []
    return [
        QAFinding(
            code="style_red_flag",
            detail=(
                "Cadence hard-stop ratio: short prose sentences exceed 60% of "
                "the passage. Merge beats or restore antecedents unless the "
                "sequence is mechanics/navigation."
            ),
        )
    ]


def _short_sentence_mask(sentences: list[_StyleSentence]) -> list[bool]:
    return [0 < sentence.word_count <= _SHORT_SENTENCE_WORD_LIMIT for sentence in sentences]


def _has_window_cluster(matches: list[bool]) -> bool:
    for start in range(len(matches)):
        if sum(matches[start : start + _STYLE_WINDOW]) >= _STYLE_CLUSTER_THRESHOLD:
            return True
    return False

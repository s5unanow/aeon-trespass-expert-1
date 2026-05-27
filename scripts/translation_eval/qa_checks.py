"""Deterministic QA checks for ensemble translation candidates.

All functions are pure and return findings as plain data. The orchestrator
(``ensemble_poc.py``) feeds them back into the Opus final-editor prompt.

Checks cover missing refs/placeholders/mechanics, glossary misses, forbidden
phrases, Russian style red flags, and coarse omission-vs-witness gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .rules import FORBIDDEN_PHRASES, GLOSSARY, GlossaryEntry

_PASSAGE_REF_RE = re.compile(r"\b0\d{3}\b")
_PLACEHOLDER_RE = re.compile(r"\[[a-z][a-z\s]+\]")
_WISDOM_RE = re.compile(r"\b([A-Z][a-z]+)\s*\((\d+)\+\)")
_DIPLOMACY_RE = re.compile(r"\b([A-Z][a-z]+)\s*([+-])(\d+)")
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
_STYLE_WINDOW = 5
_STYLE_CLUSTER_THRESHOLD = 3
_SHORT_SENTENCE_WORD_LIMIT = 4
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
        re.compile(r"\bвысадочн\w*\s+отряд\w*\b", re.IGNORECASE),
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
        re.compile(r"\bобраща\w*\s+к\s+ним\b", re.IGNORECASE),
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
class QAFinding:
    code: str
    detail: str


@dataclass(frozen=True)
class _StyleSentence:
    opener: str | None
    word_count: int
    is_you_verb: bool


def find_missing_passage_refs(en: str, ru: str) -> list[QAFinding]:
    """Return 4-digit passage refs that appear in EN but not in RU."""
    refs_en = sorted(set(_PASSAGE_REF_RE.findall(en)))
    return [QAFinding(code="missing_passage_ref", detail=ref) for ref in refs_en if ref not in ru]


def find_missing_placeholders(en: str, ru: str) -> list[QAFinding]:
    """Return bracket placeholders (``[horned symbol]``) missing from RU."""
    placeholders = sorted(set(_PLACEHOLDER_RE.findall(en)))
    return [QAFinding(code="missing_placeholder", detail=ph) for ph in placeholders if ph not in ru]


def find_missing_mechanics(en: str, ru: str) -> list[QAFinding]:
    """Return missing ``(N+)`` thresholds and ``±N`` modifiers from EN."""
    findings: list[QAFinding] = []

    for stat, threshold in _WISDOM_RE.findall(en):
        token_ru_shape = f"({threshold}+)"
        if token_ru_shape not in ru:
            findings.append(
                QAFinding(
                    code="missing_mechanics_threshold",
                    detail=f"{stat} ({threshold}+)",
                )
            )

    for stat, sign, n in _DIPLOMACY_RE.findall(en):
        token_ru_shape = f"{sign}{n}"
        if token_ru_shape not in ru:
            findings.append(
                QAFinding(
                    code="missing_mechanics_modifier",
                    detail=f"{stat} {sign}{n}",
                )
            )

    return findings


def find_glossary_misses(
    en: str,
    ru: str,
    glossary: tuple[GlossaryEntry, ...] = GLOSSARY,
) -> list[QAFinding]:
    """Return EN-side glossary terms whose RU rendering is absent.

    RU matching accepts a short canonical prefix, enough for simple declension
    such as ``Кносс`` → ``Кносса``.
    """
    en_lower = en.lower()
    ru_lower = ru.lower()
    findings: list[QAFinding] = []
    for entry in glossary:
        if entry.en.lower() not in en_lower:
            continue
        # Strip wrapping non-letter punctuation (e.g. «Арго» → Арго).
        stripped = entry.ru.strip("«»\"' ").lower()
        if not stripped:
            continue
        stem = stripped[: min(len(stripped), 5)]
        if stem not in ru_lower:
            findings.append(
                QAFinding(
                    code="glossary_miss",
                    detail=f"{entry.en} → {entry.ru}",
                )
            )
    return findings


def find_forbidden_phrases(
    ru: str,
    forbidden: tuple[str, ...] = FORBIDDEN_PHRASES,
) -> list[QAFinding]:
    """Return forbidden phrases present anywhere in the candidate RU."""
    findings: list[QAFinding] = []
    for phrase in forbidden:
        if phrase in ru:
            findings.append(QAFinding(code="forbidden_phrase", detail=phrase))
    return findings


def find_style_red_flags(ru: str) -> list[QAFinding]:
    """Return known prose failures learned from human review.

    This is intentionally narrow: deterministic QA should catch repeated,
    high-confidence bad patterns, while broader literary judgement stays with
    the model editor / human review pass.
    """
    findings: list[QAFinding] = []
    for pattern, detail in _STYLE_RED_FLAGS:
        if pattern.search(ru):
            findings.append(QAFinding(code="style_red_flag", detail=detail))

    style_sentences = _style_sentences(ru)
    findings.extend(_find_repeated_openers(style_sentences))
    findings.extend(_find_you_verb_cadence(style_sentences))
    findings.extend(_find_short_sentence_clusters(style_sentences))
    return findings


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
    verb = match.group("verb").lower()
    return verb.endswith(_YOU_VERB_SUFFIXES)


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
    is_short = [0 < sentence.word_count <= _SHORT_SENTENCE_WORD_LIMIT for sentence in sentences]
    if not _has_window_cluster(is_short):
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


def _has_window_cluster(matches: list[bool]) -> bool:
    for start in range(len(matches)):
        window = matches[start : start + _STYLE_WINDOW]
        if sum(window) >= _STYLE_CLUSTER_THRESHOLD:
            return True
    return False


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def coarse_omission_witness(
    candidate_ru: str,
    gemma_ru: str,
    drop_ratio: float = 0.20,
) -> list[QAFinding]:
    """Return paragraph/character-count drops against a Gemma witness."""
    findings: list[QAFinding] = []

    cand_paragraphs = _split_paragraphs(candidate_ru)
    witness_paragraphs = _split_paragraphs(gemma_ru)
    if len(cand_paragraphs) < len(witness_paragraphs):
        findings.append(
            QAFinding(
                code="paragraph_count_drop",
                detail=(f"candidate={len(cand_paragraphs)} witness={len(witness_paragraphs)}"),
            )
        )

    cand_chars = len(candidate_ru)
    witness_chars = len(gemma_ru)
    if witness_chars > 0:
        ratio = (witness_chars - cand_chars) / witness_chars
        if ratio > drop_ratio:
            findings.append(
                QAFinding(
                    code="char_count_drop",
                    detail=(f"candidate={cand_chars} witness={witness_chars} drop={ratio:.2%}"),
                )
            )

    return findings


def all_checks(
    en: str,
    ru: str,
    gemma_ru: str | None = None,
) -> list[QAFinding]:
    """Run every check and return the aggregated findings."""
    findings: list[QAFinding] = []
    findings.extend(find_missing_passage_refs(en, ru))
    findings.extend(find_missing_placeholders(en, ru))
    findings.extend(find_missing_mechanics(en, ru))
    findings.extend(find_glossary_misses(en, ru))
    findings.extend(find_forbidden_phrases(ru))
    findings.extend(find_style_red_flags(ru))
    if gemma_ru is not None:
        findings.extend(coarse_omission_witness(ru, gemma_ru))
    return findings

"""Deterministic QA checks for ensemble translation candidates.

All functions are pure: they take English source text plus a candidate
Russian translation (and optional rule data) and return findings as plain
data. The orchestrator (``ensemble_poc.py``) feeds the findings back into
the Opus final-editor prompt.

Findings classes:
* missing passage refs (``0001``, ``0003``, ``0047`` …)
* missing bracket placeholders (``[horned symbol]``)
* missing mechanics tokens (``Wisdom (7+)``, ``Diplomacy -1`` …)
* glossary term misses (EN term present in source but RU rendering absent)
* forbidden phrases present in the candidate
* known prose/style red flags from human review
* coarse paragraph-coverage gap vs a TranslateGemma omission witness
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .rules import FORBIDDEN_PHRASES, GLOSSARY, GlossaryEntry

_PASSAGE_REF_RE = re.compile(r"\b0\d{3}\b")
_PLACEHOLDER_RE = re.compile(r"\[[a-z][a-z\s]+\]")
_WISDOM_RE = re.compile(r"\b([A-Z][a-z]+)\s*\((\d+)\+\)")
_DIPLOMACY_RE = re.compile(r"\b([A-Z][a-z]+)\s*([+-])(\d+)")
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
        re.compile(r"звук\s+натягиваемых\s+тетив", re.IGNORECASE),
        "Awkward collocation: prefer 'звук натягиваемой тетивы' or a stronger "
        "image such as 'треск натягиваемых тетив'.",
    ),
    (
        re.compile(r"высадочный\s+отряд", re.IGNORECASE),
        "Context check: 'высадочный отряд' is often too military/technical. "
        "For shore contact prefer 'передовой отряд' or 'отряд на берег'; "
        "for clue-search or scouting prefer 'поисковый отряд' or "
        "'разведывательный отряд'.",
    ),
)


@dataclass(frozen=True)
class QAFinding:
    code: str
    detail: str


def find_missing_passage_refs(en: str, ru: str) -> list[QAFinding]:
    """Return refs that appear in EN but not in RU.

    Refs are 4-digit zero-padded tokens like ``0001``. Detection is plain
    substring presence — RU is allowed to embed the ref anywhere.
    """
    refs_en = sorted(set(_PASSAGE_REF_RE.findall(en)))
    return [QAFinding(code="missing_passage_ref", detail=ref) for ref in refs_en if ref not in ru]


def find_missing_placeholders(en: str, ru: str) -> list[QAFinding]:
    """Return bracket placeholders (``[horned symbol]``) missing from RU."""
    placeholders = sorted(set(_PLACEHOLDER_RE.findall(en)))
    return [QAFinding(code="missing_placeholder", detail=ph) for ph in placeholders if ph not in ru]


def find_missing_mechanics(en: str, ru: str) -> list[QAFinding]:
    """Return mechanics tokens that should be preserved but appear missing.

    Two shapes are supported and reported individually:

    * ``Wisdom (7+)`` — the parenthesised number+'+' suffix. RU is required
      to contain ``(N+)`` (with the same N) somewhere; the Russian rendering
      of the stat name is checked separately by the glossary check.
    * ``Diplomacy -1`` / ``Diplomacy +2`` — the ``±N`` suffix. RU must
      contain ``±N`` with the same sign and number.
    """
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
    """Return glossary entries whose EN term appears in the source page
    but whose canonical RU rendering does not appear in the candidate.

    Matching:
    * EN side: case-insensitive whole-word/substring (so 'Wisdom' matches
      both 'Wisdom (7+)' and the bare 'Wisdom').
    * RU side: case-insensitive substring. Russian morphology (declension)
      is allowed — the check looks for the *stem* form by stripping the
      trailing inflectional letters from short stems is **not** applied
      here; we instead check for the canonical RU surface form OR a
      reasonable noun-stem prefix. Concretely we look for the first
      ``min(len(ru_term), 5)`` characters of the canonical RU (lowered),
      which is enough to pass declined forms like *Кносса* vs *Кносс*.
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
    return findings


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def coarse_omission_witness(
    candidate_ru: str,
    gemma_ru: str,
    drop_ratio: float = 0.20,
) -> list[QAFinding]:
    """Return a finding when the candidate has materially fewer paragraphs
    or characters than the Gemma omission witness.

    This is the cheap, model-agnostic omission check the issue asks for.
    Gemma's known property (from S5U-775) is that it preserves paragraph
    and sentence count exactly; if the candidate is meaningfully shorter
    than Gemma, that's a coverage signal worth probing.

    Two thresholds:

    * paragraph count delta > 0 → flag.
    * char-count drop > ``drop_ratio`` (default 20 %) → flag.
    """
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
    """Run every check on a candidate and return the aggregated list.

    ``gemma_ru`` is optional — when absent, the omission-witness comparison
    is skipped. The other five checks always run.
    """
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

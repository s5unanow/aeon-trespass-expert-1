"""Deterministic QA checks for ensemble translation candidates.

All functions are pure and return findings as plain data. The orchestrator
(``ensemble_poc.py``) feeds them back into the Opus final-editor prompt.

Checks cover missing refs/placeholders/mechanics, glossary misses, forbidden
phrases, Russian style red flags, and coarse omission-vs-witness gaps.
"""

from __future__ import annotations

import re

from .qa_models import QAFinding
from .rules import FORBIDDEN_PHRASES, GLOSSARY, GlossaryEntry
from .style_qa import find_style_red_flags

_PASSAGE_REF_RE = re.compile(r"\b0\d{3}\b")
_PLACEHOLDER_RE = re.compile(r"\[[a-z][a-z\s]+\]")
_WISDOM_RE = re.compile(r"\b([A-Z][a-z]+)\s*\((\d+)\+\)")
_DIPLOMACY_RE = re.compile(r"\b([A-Z][a-z]+)\s*([+-])(\d+)")


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

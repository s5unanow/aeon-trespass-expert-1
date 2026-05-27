"""Tests for scripts/translation_eval/qa_checks.py (S5U-776)."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]


@pytest.fixture()
def qa_mod() -> Iterator[ModuleType]:
    """Load scripts.translation_eval.qa_checks with REPO on sys.path.

    Adds the repo root so the namespace package ``scripts`` and the
    regular package ``scripts.translation_eval`` (which has its own
    ``__init__.py``) resolve.
    """
    repo_str = str(REPO)
    added = repo_str not in sys.path
    if added:
        sys.path.insert(0, repo_str)
    try:
        module = importlib.import_module("scripts.translation_eval.qa_checks")
        yield module
    finally:
        if added:
            sys.path.remove(repo_str)


# ---------------------------------------------------------------------------
# Passage refs
# ---------------------------------------------------------------------------


def test_passage_refs_happy_all_present(qa_mod: ModuleType) -> None:
    en = "First 0001. Then 0003. See 0047 and 0068."
    ru = "Сначала 0001. Затем 0003. Смотри 0047 и 0068."
    assert qa_mod.find_missing_passage_refs(en, ru) == []


def test_passage_refs_failure_one_dropped(qa_mod: ModuleType) -> None:
    en = "First 0001. Then 0003. See 0047 and 0068."
    ru = "Сначала 0001. Затем 0003. Смотри 0068."  # 0047 dropped
    findings = qa_mod.find_missing_passage_refs(en, ru)
    assert [f.detail for f in findings] == ["0047"]
    assert all(f.code == "missing_passage_ref" for f in findings)


def test_passage_refs_adversarial_unrelated_digits_in_ru(qa_mod: ModuleType) -> None:
    """RU contains '7+' (mechanics) and 'page 12' (count) — no spurious flag.

    Adversarial: RU may legitimately contain other digit groups; the check
    must only look for the EN-side 4-digit refs.
    """
    en = "Test Wisdom (7+) and see 0001."
    ru = "Проверка Мудрость (7+) и смотри 0001. Также страница 12."
    assert qa_mod.find_missing_passage_refs(en, ru) == []


# ---------------------------------------------------------------------------
# Bracket placeholders
# ---------------------------------------------------------------------------


def test_placeholders_happy_present(qa_mod: ModuleType) -> None:
    en = "or gain +2 [horned symbol] for success"
    ru = "или получи +2 [horned symbol] для успеха"
    assert qa_mod.find_missing_placeholders(en, ru) == []


def test_placeholders_failure_translated(qa_mod: ModuleType) -> None:
    en = "or gain +2 [horned symbol] for success"
    ru = "или получи +2 [символ рога] для успеха"
    findings = qa_mod.find_missing_placeholders(en, ru)
    assert [f.detail for f in findings] == ["[horned symbol]"]


def test_placeholders_adversarial_brackets_in_ru_only(qa_mod: ModuleType) -> None:
    """RU has its own brackets; EN has none → no findings (we report
    EN-side placeholders missing from RU, not RU-side stray brackets).
    """
    en = "Plain text with no placeholders."
    ru = "Простой текст [примечание] без плейсхолдеров."
    assert qa_mod.find_missing_placeholders(en, ru) == []


# ---------------------------------------------------------------------------
# Mechanics tokens
# ---------------------------------------------------------------------------


def test_mechanics_threshold_happy(qa_mod: ModuleType) -> None:
    en = "Wisdom (7+) test"
    ru = "Проверка Мудрость (7+)"
    assert qa_mod.find_missing_mechanics(en, ru) == []


def test_mechanics_threshold_failure_paren_dropped(qa_mod: ModuleType) -> None:
    en = "Wisdom (7+) test"
    ru = "Проверка Мудрость 7"
    findings = qa_mod.find_missing_mechanics(en, ru)
    detail_codes = [(f.code, f.detail) for f in findings]
    assert ("missing_mechanics_threshold", "Wisdom (7+)") in detail_codes


def test_mechanics_modifier_signs_preserved(qa_mod: ModuleType) -> None:
    """Adversarial: both '+1' and '-1' in EN, RU drops the '-1' but
    keeps the '+1'. Check must report exactly the missing one.
    """
    en = "Diplomacy +1. Diplomacy -1."
    ru = "Дипломатия +1. Дипломатия 1."  # '-' lost
    findings = qa_mod.find_missing_mechanics(en, ru)
    detail_codes = [(f.code, f.detail) for f in findings]
    assert ("missing_mechanics_modifier", "Diplomacy -1") in detail_codes
    # '+1' is present on the RU side, so it must NOT be reported.
    assert ("missing_mechanics_modifier", "Diplomacy +1") not in detail_codes


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------


def test_glossary_happy_canonical_present(qa_mod: ModuleType) -> None:
    en = "Wisdom check, Knossos pier."
    ru = "Проверка Мудрости, причал Кносса."
    assert qa_mod.find_glossary_misses(en, ru) == []


def test_glossary_failure_term_missing(qa_mod: ModuleType) -> None:
    en = "Knossos pier"
    ru = "причал Кретополя"  # canonical Кносс/Кносса absent
    findings = qa_mod.find_glossary_misses(en, ru)
    detail_terms = [f.detail.split(" → ")[0] for f in findings]
    assert "Knossos" in detail_terms


def test_glossary_adversarial_declension_accepted(qa_mod: ModuleType) -> None:
    """Adversarial: RU uses the genitive form 'Кносса' rather than the
    nominative 'Кносс'. The check must accept the stem match.
    """
    en = "Knossos pier"
    ru = "причал Кносса"
    findings = qa_mod.find_glossary_misses(en, ru)
    detail_terms = [f.detail.split(" → ")[0] for f in findings]
    assert "Knossos" not in detail_terms


# ---------------------------------------------------------------------------
# Forbidden phrases
# ---------------------------------------------------------------------------


def test_forbidden_happy_clean(qa_mod: ModuleType) -> None:
    ru = "«Арго» рассекает вечерние волны."
    assert qa_mod.find_forbidden_phrases(ru) == []


def test_forbidden_failure_detected(qa_mod: ModuleType) -> None:
    ru = "«Арго» режет вечерние волны."
    findings = qa_mod.find_forbidden_phrases(ru)
    assert any(f.detail == "режет вечерние волны" for f in findings)
    assert all(f.code == "forbidden_phrase" for f in findings)


def test_forbidden_adversarial_overlapping(qa_mod: ModuleType) -> None:
    """Adversarial: RU has 'Гвардия' (the Latinism we ban) embedded in a
    longer compound. Substring detection must still fire.
    """
    ru = "Здесь стояла Гвардия Рогатых."
    findings = qa_mod.find_forbidden_phrases(ru)
    assert any(f.detail == "Гвардия" for f in findings)


def test_forbidden_promotes_review_memory_scene_terms(qa_mod: ModuleType) -> None:
    ru = (
        "После недолгих споров вы решаете отправить на берег высадочный отряд "
        "и выделить послам вооружённый эскорт."
    )
    details = [f.detail for f in qa_mod.find_forbidden_phrases(ru)]

    assert "отправить на берег высадочный отряд" in details
    assert "вооружённый эскорт" in details


# ---------------------------------------------------------------------------
# Style red flags
# ---------------------------------------------------------------------------


def test_style_red_flag_contextual_fragment_error(qa_mod: ModuleType) -> None:
    ru = "Когда город озарился лампами.\n\nНо лишь немногих."
    findings = qa_mod.find_style_red_flags(ru)
    assert any(f.code == "style_red_flag" and "lamps" in f.detail for f in findings)


def test_style_red_flag_gamebook_note_command(qa_mod: ModuleType) -> None:
    ru = "Запомните «параграф 0003». (пока не переходите к нему!)"
    findings = qa_mod.find_style_red_flags(ru)
    assert any("Gamebook convention" in f.detail for f in findings)


@pytest.mark.parametrize(
    ("ru", "detail_part"),
    [
        ("на страже стоит Стража Рогатых", "Tautology"),
        ("См. 0068.", "Gamebook navigation"),
        ("к Минойцам подошли послы", "Demonym"),
        ("к минойцам подошли послы", ""),
        ("Минойцы: Дипломатия -1", ""),
        ("Рогатого Города", "lowercase"),
        ("До вашего слуха доносится знакомый звук натягиваемых тетив.", "Awkward collocation"),
        ("На рассвете вы отправляете высадочный отряд.", "Context check"),
    ],
)
def test_style_red_flags_cover_review_patterns(
    qa_mod: ModuleType,
    ru: str,
    detail_part: str,
) -> None:
    findings = qa_mod.find_style_red_flags(ru)
    if not detail_part:
        assert findings == []
    else:
        assert any(detail_part in f.detail for f in findings)


# ---------------------------------------------------------------------------
# Coarse omission witness
# ---------------------------------------------------------------------------


def test_omission_happy_equal_paragraphs(qa_mod: ModuleType) -> None:
    candidate = "Para 1.\n\nPara 2.\n\nPara 3."
    witness = "Пара 1.\n\nПара 2.\n\nПара 3."
    assert qa_mod.coarse_omission_witness(candidate, witness) == []


def test_omission_failure_paragraph_drop(qa_mod: ModuleType) -> None:
    candidate = "Пара 1.\n\nПара 3."  # one para dropped
    witness = "Пара 1.\n\nПара 2.\n\nПара 3."
    findings = qa_mod.coarse_omission_witness(candidate, witness)
    codes = [f.code for f in findings]
    assert "paragraph_count_drop" in codes


def test_omission_adversarial_char_drop_within_paragraphs(qa_mod: ModuleType) -> None:
    """Adversarial: paragraph counts equal but candidate body is much
    shorter than witness — char-count drop must still fire.
    """
    candidate = "Пара 1.\n\nПара 2.\n\nПара 3."
    witness = (
        "Очень длинная первая полная по содержанию пара один с описаниями.\n\n"
        "Очень длинная вторая полная по содержанию пара два с деталями.\n\n"
        "Очень длинная третья полная по содержанию пара три с примерами."
    )
    findings = qa_mod.coarse_omission_witness(candidate, witness, drop_ratio=0.20)
    codes = [f.code for f in findings]
    assert "char_count_drop" in codes


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def test_all_checks_aggregates_and_skips_omission_when_no_witness(
    qa_mod: ModuleType,
) -> None:
    en = "Knossos pier 0001 [horned symbol] Wisdom (7+)"
    ru = "причал Кносса 0001 [horned symbol] Мудрость (7+)"
    # No witness → omission check skipped, all clean.
    assert qa_mod.all_checks(en, ru, gemma_ru=None) == []
    # With identical witness → still clean.
    assert qa_mod.all_checks(en, ru, gemma_ru=ru) == []


def test_all_checks_includes_style_red_flags(qa_mod: ModuleType) -> None:
    findings = qa_mod.all_checks("See 0068.", "См. 0068.", gemma_ru=None)

    assert any(f.code == "style_red_flag" for f in findings)

# ruff: noqa: RUF001  — Russian style examples are intentional.
"""S5U-803 threshold tests for translation style QA."""

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
    repo_str = str(REPO)
    added = repo_str not in sys.path
    if added:
        sys.path.insert(0, repo_str)
    try:
        yield importlib.import_module("scripts.translation_eval.qa_checks")
    finally:
        if added:
            sys.path.remove(repo_str)


def _details(findings: list[object]) -> str:
    return "\n".join(str(finding.detail) for finding in findings)


def test_repeated_openers_requires_four_hits_in_six_sentences(qa_mod: ModuleType) -> None:
    ru = (
        "Вы входите в притихший город. "
        "Вы слышите шаги за спиной. "
        "На площади гаснут последние огни. "
        "Вы замечаете движение у ворот."
    )

    findings = qa_mod.find_style_red_flags(ru)

    assert "repeated opener 'Вы'" not in _details(findings)


def test_repeated_openers_still_flags_dense_cluster(qa_mod: ModuleType) -> None:
    ru = (
        "Вы входите в притихший город. "
        "Вы слышите шаги за спиной. "
        "На площади гаснут последние огни. "
        "Вы замечаете движение у ворот. "
        "Вдали звучит труба. "
        "Вы ждёте ответа."
    )

    findings = qa_mod.find_style_red_flags(ru)

    assert "repeated opener 'Вы'" in _details(findings)


def test_short_sentence_cluster_requires_four_hits(qa_mod: ModuleType) -> None:
    ru = "Тишина. Ветер стих. Вы ждёте. Над воротами меркнут последние огни."

    findings = qa_mod.find_style_red_flags(ru)

    assert "short prose sentences" not in _details(findings)


def test_hard_stop_ratio_flags_sustained_choppy_prose(qa_mod: ModuleType) -> None:
    ru = (
        "Тишина. Ветер стих. Вы ждёте. Ответа нет. "
        "Свет меркнет. Камень холоден. Стража молчит. Тропа пуста."
    )

    findings = qa_mod.find_style_red_flags(ru)

    assert "hard-stop ratio" in _details(findings)


def test_short_sentence_clusters_do_not_cross_paragraph_boundaries(
    qa_mod: ModuleType,
) -> None:
    ru = "Тишина.\n\nВетер стих.\n\nВы ждёте.\n\nОтвета нет."

    findings = qa_mod.find_style_red_flags(ru)

    assert findings == []


def test_generic_addressing_is_not_a_collocation_flag(qa_mod: ModuleType) -> None:
    ru = "Писец спокойно обращается к ним по очереди и сверяет имена."

    findings = qa_mod.find_style_red_flags(ru)

    assert findings == []


def test_prophetic_addressing_context_still_flags(qa_mod: ModuleType) -> None:
    ru = "Нищий обращается к ним, словно жрец древних времен."

    findings = qa_mod.find_style_red_flags(ru)

    assert "public prophetic address" in _details(findings)


def test_landing_party_without_scene_context_is_not_a_collocation_flag(
    qa_mod: ModuleType,
) -> None:
    ru = "После шторма высадочный отряд закрепляет канаты у разбитого причала."

    findings = qa_mod.find_style_red_flags(ru)

    assert findings == []


def test_landing_party_shore_contact_context_still_flags(qa_mod: ModuleType) -> None:
    ru = "Вы отправляете на берег высадочный отряд для встречи с минойцами."

    findings = qa_mod.find_style_red_flags(ru)

    assert "scene function" in _details(findings)

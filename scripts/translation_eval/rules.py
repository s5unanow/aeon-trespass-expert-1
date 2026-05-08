"""Project-specific glossary, forbidden phrases, and bad/good examples.

The constants here are deliberately small and editable — the ensemble POC
(``ensemble_poc.py``) reads them once per page and embeds them into the
Sonnet/Opus system prompts and into the deterministic QA checks
(``qa_checks.py``).

Three categories are tracked separately, as the issue asks:

* GLOSSARY — fixed term renderings (EN → canonical RU). The QA checks fail
  when the EN side appears in the source page but the RU side is absent
  from the candidate translation.
* FORBIDDEN_PHRASES — observed bad RU outputs from the S5U-775 eval. A
  candidate translation that contains any of these is flagged.
* BAD_GOOD_EXAMPLES — phrase-level rewrites used as few-shot guidance
  inside the translator/editor prompts.

Sources:
* S5U-775 ``tmp/translation-eval/comparison.md`` — terminology vote.
* S5U-776 issue body — bad/good phrase pairs and forbidden outputs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlossaryEntry:
    en: str
    ru: str
    note: str = ""


GLOSSARY: tuple[GlossaryEntry, ...] = (
    GlossaryEntry("Wisdom", "Мудрость"),
    GlossaryEntry("Diplomacy", "Дипломатия"),
    GlossaryEntry("Insight", "Прозрение"),
    GlossaryEntry("Survival", "Выживание"),
    GlossaryEntry("Knossos", "Кносс", note="genitive: Кносса; not 'Кноса'"),
    GlossaryEntry("Minoans", "Минойцы", note="not 'Миносцы'"),
    GlossaryEntry("Argo", "«Арго»"),
    GlossaryEntry("Argonaut", "Аргонавт"),
    GlossaryEntry("Minotaur", "Минотавр"),
    GlossaryEntry("Daedalus Vault", "Хранилище Дедала"),
    GlossaryEntry("Horned City", "Рогатый Город"),
    GlossaryEntry(
        "Horned Guard",
        "Стража",
        note="archaic-Greek register; avoid Latinism 'Гвардия'",
    ),
    GlossaryEntry(
        "Hornsworn",
        "Рогоприсягнувшие",
        note="preserves 'sworn' connotation; do NOT conflate with 'Стража'",
    ),
    GlossaryEntry("Old Priest", "Старый Жрец", note="title-case both words"),
    GlossaryEntry("Phaedra", "Федра"),
    GlossaryEntry("Minos", "Минос"),
    GlossaryEntry("Androgeos", "Андрогей"),
)


FORBIDDEN_PHRASES: tuple[str, ...] = (
    "режет вечерние волны",
    "С великим трепетом",
    "с великим трепетом",
    "обошло древний мегаполис",
    "Гвардия",
)


@dataclass(frozen=True)
class BadGoodExample:
    en: str
    bad_ru: str
    good_ru: str
    why: str


BAD_GOOD_EXAMPLES: tuple[BadGoodExample, ...] = (
    BadGoodExample(
        en="The Argo cuts through the evening waves",
        bad_ru="«Арго» режет вечерние волны.",
        good_ru="«Арго» рассекает вечерние волны.",
        why="'режет' is a flat literal calque; 'рассекает' is the literary "
        "Russian verb for a ship cleaving the sea.",
    ),
    BadGoodExample(
        en="With great trepidation, the crew watches the shoreline for any signs of danger.",
        bad_ru="Экипаж с великим трепетом вглядывается в берег.",
        good_ru="С большой тревогой команда наблюдает за береговой линией, "
        "высматривая признаки опасности.",
        why="'с великим трепетом' over-translates and drops the modifying "
        "clause 'for any signs of danger'. Keep the modifier.",
    ),
    BadGoodExample(
        en="the calamity passed by the ancient metropolis",
        bad_ru="бедствие обошло древний мегаполис",
        good_ru="бедствие обошло стороной древнюю метрополию",
        why="'мегаполис' is a modern register; this is an archaic Greek "
        "setting. 'обошло стороной' is the natural Russian idiom for "
        "'passed by' a place.",
    ),
    BadGoodExample(
        en="the Horned Guard stand watch",
        bad_ru="стоит на страже Гвардия Рогатых",
        good_ru="на страже стоит Стража Рогатых",
        why="Latinism 'Гвардия' clashes with archaic-Greek register; use "
        "'Стража' for Horned Guard.",
    ),
    BadGoodExample(
        en="Wisdom (7+) test",
        bad_ru="проверка Мудрость 7",
        good_ru="проверка Мудрости (7+)",
        why="Mechanics tokens (Wisdom (7+), Diplomacy +1/-1) must preserve "
        "parentheses, '+', and '-' verbatim.",
    ),
)


REVIEWER_RUBRIC: tuple[str, ...] = (
    "semantic fidelity — every English clause is preserved",
    "natural Russian — no calques or word-for-word artefacts",
    "genre/register — archaic/mythic Greek tone, not modern news/business",
    "terminology — glossary terms render consistently within and across pages",
    "mechanics preservation — passage refs, bracket placeholders, "
    "Wisdom (N+), Diplomacy +/-N kept verbatim",
)

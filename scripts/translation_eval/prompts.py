"""System / user prompt builders for the ensemble POC.

Three prompt shapes:

* Sonnet variant prompts — three different style "lenses" producing three
  RU drafts per page. Same glossary / examples / mechanics rules each
  time; only the closing instruction differs.
* Opus synthesis prompt — receives EN + 3 Sonnet variants + glossary /
  rules and emits one synthesised RU draft.
* Opus repair prompt — receives the current RU draft + the
  TranslateGemma-derived omission findings + glossary / rules and emits
  a *minimally* repaired draft.

The strings here are deliberately kept inline (no I/O) so they're cheap
to inspect and iterate on, and so the orchestrator can paste them into
the report alongside the model outputs for human review.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import BAD_GOOD_EXAMPLES, FORBIDDEN_PHRASES, GLOSSARY, REVIEWER_RUBRIC


@dataclass(frozen=True)
class SonnetVariant:
    name: str
    style_lens: str
    extra_instruction: str


SONNET_VARIANTS: tuple[SonnetVariant, ...] = (
    SonnetVariant(
        name="literal-fidelity",
        style_lens="literal-fidelity",
        extra_instruction=(
            "Translate as literally as is compatible with grammatical "
            "Russian. Preserve every clause, every modifier, every "
            "negation. Do not paraphrase — if the English is awkward, "
            "the Russian may also be slightly awkward. Your goal here "
            "is coverage, not elegance."
        ),
    ),
    SonnetVariant(
        name="literary-prose",
        style_lens="literary-prose",
        extra_instruction=(
            "Translate as literary Russian prose suitable for an "
            "ancient-Greek mythic gamebook. Choose verbs and nouns that "
            "evoke the period (e.g. 'рассекает' for a ship cleaving "
            "water; 'наблюдает' for watching with care). Avoid "
            "Latinisms (e.g. prefer 'Стража' to 'Гвардия'). Preserve "
            "every clause, but prioritise natural Russian rhythm."
        ),
    ),
    SonnetVariant(
        name="idiomatic-natural",
        style_lens="idiomatic-natural",
        extra_instruction=(
            "Translate so that a native Russian reader hears natural "
            "speech. Where the English uses an idiom or set phrase, "
            "find the Russian equivalent (e.g. 'passed by' → 'обошло "
            "стороной', not 'обошло'). Avoid calques. Preserve every "
            "clause; do not invent material."
        ),
    ),
)


def _format_glossary() -> str:
    lines = ["Glossary (canonical EN → RU; use these renderings consistently):"]
    for entry in GLOSSARY:
        suffix = f"  ({entry.note})" if entry.note else ""
        lines.append(f"  - {entry.en} → {entry.ru}{suffix}")
    return "\n".join(lines)


def _format_forbidden() -> str:
    lines = ["Forbidden phrases (do NOT emit these — they were rejected in S5U-775 review):"]
    for phrase in FORBIDDEN_PHRASES:
        lines.append(f"  - {phrase!r}")
    return "\n".join(lines)


def _format_examples() -> str:
    lines = ["Bad → Good rewrites (learn the pattern, do not memorise the strings):"]
    for ex in BAD_GOOD_EXAMPLES:
        lines.append(f"  EN: {ex.en}")
        lines.append(f"  BAD: {ex.bad_ru}")
        lines.append(f"  GOOD: {ex.good_ru}")
        lines.append(f"  WHY: {ex.why}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_rubric() -> str:
    lines = ["Reviewer rubric (the human reviewer scores on these axes):"]
    for axis in REVIEWER_RUBRIC:
        lines.append(f"  - {axis}")
    return "\n".join(lines)


_MECHANICS_RULES = (
    "Mechanics preservation (HARD requirements):\n"
    "  - Preserve passage reference numbers verbatim, e.g. 0001, 0003, 0047, 0068.\n"
    "  - Preserve bracketed placeholders verbatim, e.g. [horned symbol].\n"
    "  - Preserve numeric tests like 'Wisdom (7+)' as 'Мудрость (7+)' "
    "(keep the parentheses and the '+').\n"
    "  - Preserve modifiers like 'Diplomacy +1' / 'Diplomacy -1' as "
    "'Дипломатия +1' / 'Дипломатия -1' (keep sign and number).\n"
    "  - Convert English curly quotes (“” ‘’) to "
    "Russian guillemets « ». Inner quotes use „ “.\n"
    "  - Preserve em-dashes and en-dashes verbatim.\n"
    "  - Preserve original paragraph breaks and line structure exactly."
)


def build_sonnet_system_prompt(variant: SonnetVariant) -> str:
    """Build the Sonnet system prompt for one of the three style variants."""
    sections = [
        f"You are a senior English→Russian literary translator working on "
        f"an ancient-Greek mythic-fantasy tabletop gamebook. Your current "
        f"task is the *{variant.style_lens}* draft.",
        variant.extra_instruction,
        _MECHANICS_RULES,
        _format_glossary(),
        _format_forbidden(),
        _format_examples(),
        _format_rubric(),
        "Output ONLY the Russian translation. No preamble, no headers, "
        "no commentary, no explanation, no markdown fences. Begin "
        "immediately with the first paragraph.",
    ]
    return "\n\n".join(sections)


def build_opus_synthesis_system_prompt() -> str:
    """Build the Opus prompt for synthesising the best draft from variants."""
    sections = [
        "You are the senior editor on an English→Russian literary "
        "translation of an ancient-Greek mythic-fantasy tabletop "
        "gamebook. You have been given the English source page and "
        "three independent Russian drafts from a translator. Your job "
        "is to synthesise ONE best Russian draft, drawing the best "
        "phrasing from each variant where they differ and falling back "
        "to your own judgement only when none of the three are good.",
        "Hard rules:\n"
        "  - You may NOT introduce material that is not in the English "
        "source. If a Russian draft has invented detail, drop it.\n"
        "  - You may NOT skip clauses that ARE in the English source, "
        "even if all three drafts dropped them.\n"
        "  - When the variants disagree on a glossary term, follow the "
        "glossary below — not the majority vote.\n"
        "  - When you have to invent phrasing yourself, prefer the "
        "*literary-prose* lens over the *literal* one.",
        _MECHANICS_RULES,
        _format_glossary(),
        _format_forbidden(),
        _format_examples(),
        _format_rubric(),
        "Output ONLY the synthesised Russian translation. No preamble, "
        "no headers, no commentary, no explanation, no markdown fences. "
        "Begin immediately with the first paragraph.",
    ]
    return "\n\n".join(sections)


def build_opus_synthesis_user_message(
    en_text: str,
    variants: list[tuple[str, str]],
) -> str:
    """Build the Opus synthesis user message with EN + 3 variants."""
    parts = ["ENGLISH SOURCE:", "<en>", en_text.rstrip(), "</en>", ""]
    for name, ru_text in variants:
        parts.append(f"VARIANT: {name}")
        parts.append(f"<{name}>")
        parts.append(ru_text.rstrip())
        parts.append(f"</{name}>")
        parts.append("")
    parts.append(
        "Now synthesise ONE best Russian draft following the rules in "
        "your system prompt. Output only the Russian text."
    )
    return "\n".join(parts)


def build_opus_repair_system_prompt() -> str:
    """Build the Opus prompt for the minimal-repair pass."""
    sections = [
        "You are the senior editor making a MINIMAL repair pass on a "
        "Russian translation. You have the English source, the current "
        "Russian draft, and a list of QA findings (omissions, glossary "
        "misses, forbidden phrases, mechanics violations).",
        "Hard rules:\n"
        "  - Make the SMALLEST edit that resolves each finding. Do NOT "
        "rewrite paragraphs that have no findings.\n"
        "  - Do NOT introduce stylistic changes beyond what each "
        "finding requires. The reviewer specifically wants minimal "
        "diff in this stage.\n"
        "  - If a finding is a 'paragraph_count_drop' or "
        "'char_count_drop' relative to a witness translation, locate "
        "the missing English clause/paragraph in the source and add "
        "the missing Russian rendering — do NOT pad with filler.\n"
        "  - If a finding is a glossary miss, replace the wrong "
        "rendering with the canonical one ONCE per occurrence; do not "
        "alter surrounding prose unnecessarily.",
        _MECHANICS_RULES,
        _format_glossary(),
        _format_forbidden(),
        "Output ONLY the repaired Russian translation. No preamble, no "
        "headers, no commentary, no diff markers, no markdown fences. "
        "Begin immediately with the first paragraph.",
    ]
    return "\n\n".join(sections)


def build_opus_repair_user_message(
    en_text: str,
    current_ru: str,
    findings: list[str],
) -> str:
    """Build the Opus repair user message."""
    parts = [
        "ENGLISH SOURCE:",
        "<en>",
        en_text.rstrip(),
        "</en>",
        "",
        "CURRENT RUSSIAN DRAFT:",
        "<ru>",
        current_ru.rstrip(),
        "</ru>",
        "",
        "QA FINDINGS (resolve each one with the smallest possible edit):",
    ]
    if not findings:
        parts.append("  (none)")
    else:
        for finding in findings:
            parts.append(f"  - {finding}")
    parts.append("")
    parts.append("Apply the minimal repair and output only the repaired Russian translation.")
    return "\n".join(parts)

"""System / user prompt builders for the ensemble POC.

Three prompt shapes:

* AGY variant prompts — three different style "lenses" producing three
  RU drafts per page. Same glossary / examples / mechanics rules each
  time; only the closing instruction differs.
* Opus synthesis prompt — receives EN + 3 AGY variants + glossary /
  rules and emits one synthesised RU draft.
* Opus final-editor prompt — receives the current RU draft + deterministic
  findings + glossary / rules and emits a polished final draft.

The strings here are deliberately kept inline (no I/O) so they're cheap
to inspect and iterate on, and so the orchestrator can paste them into
the report alongside the model outputs for human review.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import BAD_GOOD_EXAMPLES, FORBIDDEN_PHRASES, GLOSSARY, REVIEWER_RUBRIC


@dataclass(frozen=True)
class TranslationVariant:
    name: str
    style_lens: str
    extra_instruction: str


TRANSLATION_VARIANTS: tuple[TranslationVariant, ...] = (
    TranslationVariant(
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
    TranslationVariant(
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
    TranslationVariant(
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

# Back-compat for older local scripts/imports. New code should use
# TRANSLATION_VARIANTS because the stage is no longer Sonnet-specific.
SONNET_VARIANTS = TRANSLATION_VARIANTS


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


_STYLE_RULES = (
    "Russian literary style rules (QUALITY requirements):\n"
    "  - The output should read like publishable Russian gamebook prose, "
    "not a line-by-line machine translation.\n"
    "  - Preserve meaning, but freely recast syntax when Russian rhythm "
    "requires it: split overloaded English sentences, merge fragments with "
    "their antecedent, and choose natural collocations.\n"
    "  - Resolve short fragments, pronouns, ellipses, and phrases such as "
    "'But only a few' from nearby context before translating them.\n"
    "  - Use standard Russian dialogue punctuation with dashes where it "
    "sounds natural; do not force English quote structure into Russian.\n"
    "  - Gamebook commands such as 'Note passage NNNN' mean record/mark it "
    "for later; prefer 'Отметьте' or 'Запишите' over 'Запомните'.\n"
    "  - Standalone gamebook navigation such as 'See 0068.' means go to "
    "that passage; prefer 'Перейдите к 0068.' over 'См. 0068.'.\n"
    "  - Avoid modern administrative/business register unless the source "
    "requires it. This setting is mythic-fantasy with ancient-Greek texture.\n"
    "  - Demonyms and generic nouns are lowercase in running Russian prose "
    "unless they are true proper names or formal UI/card titles.\n"
    "  - Never preserve a literal phrase merely because it is structurally "
    "close to the English. Prefer the best Russian sentence that carries "
    "the same scene beat.\n"
    "  - Do not add new plot facts, but do make concise implicit antecedents, "
    "physical causes, and scene relations explicit when Russian needs them."
)


def build_variant_system_prompt(variant: TranslationVariant) -> str:
    """Build the translator prompt for one of the three style variants."""
    sections = [
        f"You are a senior English→Russian literary translator working on "
        f"an ancient-Greek mythic-fantasy tabletop gamebook. Your current "
        f"task is the *{variant.style_lens}* draft.",
        variant.extra_instruction,
        _MECHANICS_RULES,
        _STYLE_RULES,
        _format_glossary(),
        _format_forbidden(),
        _format_examples(),
        _format_rubric(),
        "Output ONLY the Russian translation. No preamble, no headers, "
        "no commentary, no explanation, no markdown fences. Begin "
        "immediately with the first paragraph.",
    ]
    return "\n\n".join(sections)


def build_sonnet_system_prompt(variant: TranslationVariant) -> str:
    """Deprecated compatibility wrapper for pre-AGY local scripts."""
    return build_variant_system_prompt(variant)


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
        "  - You may NOT introduce new plot facts that are not in the English "
        "source. If a Russian draft invents detail, drop it. Controlled "
        "explicitation of implicit antecedents, physical causes, and scene "
        "relations is allowed when Russian needs it.\n"
        "  - You may NOT skip clauses that ARE in the English source, "
        "even if all three drafts dropped them.\n"
        "  - When the variants disagree on a glossary term, follow the "
        "glossary below — not the majority vote.\n"
        "  - When you have to invent phrasing yourself, prefer the "
        "*literary-prose* lens over the *literal* one.",
        "Editorial selection rules:\n"
        "  - Do not average the three variants. Select and combine the best "
        "phrases sentence by sentence, exactly like a human editor choosing "
        "between several proposed Russian renderings.\n"
        "  - If one variant is more faithful but another has better Russian "
        "rhythm, keep the faithful meaning and adopt the better rhythm.\n"
        "  - If all variants sound literal, write a new Russian sentence "
        "that satisfies the source and the style guide.\n"
        "  - Prefer vivid but controlled literary Russian. Avoid padding, "
        "purple prose, and invented facts.",
        _MECHANICS_RULES,
        _STYLE_RULES,
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
    """Build the Opus prompt for the final literary editor pass."""
    sections = [
        "You are the senior literary editor making the final pass on a "
        "Russian translation. You have the English source, the current "
        "Russian draft, and deterministic QA findings when any were found "
        "(omissions, glossary misses, forbidden phrases, mechanics "
        "violations).",
        "Hard rules:\n"
        "  - Resolve each QA finding and each obvious literary-quality "
        "failure. A paragraph with flat literal Russian, bad antecedent "
        "resolution, or awkward dialogue is in scope for repair even if "
        "deterministic QA did not flag it.\n"
        "  - Keep mechanics, references, placeholders, and glossary terms "
        "stable. Do not rewrite clean paragraphs only for variety.\n"
        "  - If a finding is a 'paragraph_count_drop' or "
        "'char_count_drop' relative to a witness translation, locate "
        "the missing English clause/paragraph in the source and add "
        "the missing Russian rendering — do NOT pad with filler.\n"
        "  - If a finding is a glossary miss, replace the wrong "
        "rendering with the canonical one ONCE per occurrence; do not "
        "alter surrounding prose unnecessarily.",
        _MECHANICS_RULES,
        _STYLE_RULES,
        _format_glossary(),
        _format_forbidden(),
        _format_examples(),
        _format_rubric(),
        "Output ONLY the edited Russian translation. No preamble, no "
        "headers, no commentary, no diff markers, no markdown fences. "
        "Begin immediately with the first paragraph.",
    ]
    return "\n\n".join(sections)


def build_opus_repair_user_message(
    en_text: str,
    current_ru: str,
    findings: list[str],
) -> str:
    """Build the Opus final-editor user message."""
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
        "QA FINDINGS (resolve each one; if none, still perform the literary editor pass):",
    ]
    if not findings:
        parts.append(
            "  (none from deterministic QA; still fix literal prose, bad "
            "antecedents, awkward dialogue, and unnatural Russian rhythm)"
        )
    else:
        for finding in findings:
            parts.append(f"  - {finding}")
    parts.append("")
    parts.append("Apply the final editor pass and output only the edited Russian translation.")
    return "\n".join(parts)

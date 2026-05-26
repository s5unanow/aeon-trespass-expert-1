# ruff: noqa: RUF001  — Cyrillic text in translation examples is intentional.
"""Build LLM prompts from TranslationBatchV1 and concept constraints."""

from __future__ import annotations

import json

from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1

_SYSTEM_PROMPT = """\
You are an expert board-game rulebook translator specialising in \
English → Russian translation. You translate structured JSON segments \
that may contain inline icon nodes, cross-references, and glossary terms.

RULES — follow every rule exactly:
1. Translate only text nodes (type="text"). Copy every non-text node \
   (type="icon", "figure_ref", "xref", "line_break", "term_mark") \
   UNCHANGED — same fields, same values, same position relative to \
   surrounding text.
2. The output MUST contain EXACTLY the same icon nodes as the input — \
   same count, same order, same symbol_id and instance_id values. \
   NEVER invent, add, or remove icon nodes. If the source has 0 icons, \
   the target must have 0 icons.
3. Use the EXACT Russian surface forms listed in the terminology section \
   below. If a concept has allowed_surface_forms, pick the grammatically \
   correct one. Never use a forbidden translation.
4. Preserve emphasis marks (bold, italic) on text nodes where appropriate \
   for Russian typography.
5. Output valid JSON matching the schema exactly — no markdown, no \
   commentary, no extra keys.
6. Produce publishable Russian, not merely structurally valid Russian. \
   Preserve meaning, but recast syntax when Russian needs it: split \
   overloaded sentences, resolve fragments from adjacent context, and \
   choose idiomatic collocations over English word order.
7. Use a mythic-fantasy / ancient-Greek gamebook register. Avoid modern \
   administrative or business phrasing unless the source requires it. \
   Demonyms and generic nouns are lowercase in running Russian prose \
   unless they are true proper names or formal UI/card titles.
8. For gamebook commands, "Note passage NNNN" means record/mark the \
   passage for later; prefer "Отметьте" or "Запишите", not \
   "Запомните". "See NNNN" means navigate to that passage; prefer \
   "Перейдите к NNNN", not "См. NNNN". For short fragments such as \
   "But only a few", use the adjacent context to restore the antecedent \
   before translating.
9. Do not add new plot facts, but do make concise implicit antecedents, \
   physical causes, and scene relations explicit when Russian needs them.
"""

_STYLE_MEMORY = """\
STYLE MEMORY — learn these patterns:
- EN: So it begins
  BAD: Так начинается
  GOOD: Так берет свое начало это сказание.
  WHY: opening lines should establish mythic storybook register.
- EN: When darkness finally comes
  BAD: Когда наконец наступает тьма
  GOOD: Когда наконец опускается тьма
  WHY: use natural Russian literary collocations.
- EN: With great trepidation, the crew watches the shoreline for any signs of danger.
  BAD: Экипаж с великим трепетом вглядывается в берег.
  GOOD: С замиранием сердца экипаж всматривается в приближающийся берег в поисках знаков угрозы.
  WHY: avoid ornate calques while preserving the danger-search modifier.
- EN: the calamity passed by the ancient metropolis
  BAD: бедствие обошло древний мегаполис
  GOOD: беда обошла стороной древний оплот
  WHY: avoid modern administrative nouns such as "мегаполис/метрополия" when context allows.
- EN: Wisdom (7+) test
  BAD: проверка Мудрости 7+
  GOOD: проверка Мудрости (7+)
  WHY: preserve mechanics punctuation exactly.
- EN: But only a few.
  BAD: Но лишь немногих.
  GOOD: Но зажглись лишь немногие из них.
  WHY: resolve the antecedent from adjacent context; here it refers to lamps.
- EN: the Horned Guard stand watch
  BAD: на страже стоит Стража Рогатых
  GOOD: Вход охраняет Рогатая стража.
  WHY: avoid tautology while preserving the term.
- EN: Note "passage 0003."
  BAD: Запомните «параграф 0003».
  GOOD: Отметьте «параграф 0003».
  WHY: gamebook note commands mean record/mark, not memorize.
- EN: See 0068.
  BAD: См. 0068.
  GOOD: Перейдите к 0068.
  WHY: standalone gamebook navigation should be an instruction to go to a passage.
- EN: after your rude awakening
  BAD: после вашего грубого пробуждения
  GOOD: после тяжелого пробуждения
  WHY: avoid literal adjective calques when Russian has a natural phrasing.
- EN: only embers remain
  BAD: Теперь остались лишь угли.
  GOOD: Теперь же от этого пламени остались лишь угли.
  WHY: restore implied antecedents when the Russian image would otherwise sound abrupt.
- EN: if the Argo is to sail the high seas again
  BAD: если «Арго» вновь выйдет в открытое море
  GOOD: если «Арго» суждено вновь выйти в открытое море
  WHY: preserve mythic fate/necessity when "is to" carries that tone.
- EN: a thing only Minos can provide
  BAD: а это может предоставить лишь Минос
  GOOD: однако открыть его может только сам Минос
  WHY: replace abstract bureaucratic phrasing with concrete scene action.
- EN: The engineers say
  BAD: Инженеры говорят
  GOOD: Мастера в один голос твердят
  WHY: mythic technology can sound more organic with "мастера" than modern "инженеры".
- EN: ambrosia to sate them
  BAD: амброзии, которой надобно их питать
  GOOD: амброзии, служащей им топливом
  WHY: prefer readable functional Russian over ornate literal phrasing.
- EN: replacement parts only the great Daedalus Vault may contain
  BAD: запасных частей, что можно найти лишь в великом Хранилище Дедала
  GOOD: редких деталей, сокрытых в великом Хранилище Дедала
  WHY: literary compression is preferred when it preserves the source.
- EN: not having set foot on dry land for many days now
  BAD: уже много дней они не ступали на твёрдую землю
  GOOD: уже много дней они не чувствовали под ногами твердой земли
  WHY: use embodied Russian imagery for physical experience.
- EN: a few envoys and an armed escort
  BAD: несколько послов и вооружённый эскорт
  GOOD: нескольких послов под прикрытием вооруженной охраны
  WHY: render the tactical relationship, not a formal procession.
- EN: You hear the familiar sound of bowstrings tightening.
  BAD: До вашего слуха доносится знакомый звук натягиваемых тетив.
  GOOD: До вас доносится знакомый звук натягиваемой тетивы.
  WHY: Russian normally treats this as one perceived sound/source; use plural
       only with a stronger image such as "треск натягиваемых тетив".
- EN: you send an away team to a mist-shrouded key
  BAD: вы отправляете высадочный отряд к окутанному туманом островку
  GOOD: вы отправляете поисковый отряд к окутанному туманом островку
  WHY: choose the Russian noun by scene function. For clue-search use
       "поисковый" or "разведывательный"; reserve "высадочный" for landing.
- EN: The pier is all but deserted
  BAD: Пристань почти пустынна
  GOOD: Пристань почти безлюдна
  WHY: use the natural word for a place with almost no people.
- EN: addressing them, like a priest of old
  BAD: обращается к ним, словно жрец древних времён
  GOOD: взывающего к ним, подобно жрецу былых веков
  WHY: public speech scenes need stronger literary verbs than generic "говорит/обращается".
- EN: squalor of splendor
  BAD: убожество великолепия
  GOOD: нищету величия
  WHY: rhetorical contrast should sound like Russian speech, not a dictionary pairing.
- EN: I clung to meaning for far too long
  BAD: Я слишком долго держался за смысл
  GOOD: Я слишком долго искал во всем высший смысл
  WHY: translate the character's prophetic intent, not the English preposition.
- EN: You quicken your pace; you have no patience for raving madmen.
  BAD: Вы ускоряете шаг — у вас нет терпения на бредящих безумцев.
  GOOD: Вы прибавляете шагу — у вас нет времени на бредни сумасшедшего.
  WHY: prefer idiomatic movement and motive phrases.
- EN: Only the Truth matters, though it is bitter!
  BAD: Лишь Истина имеет значение, пусть она и горька!
  GOOD: Важна лишь Истина, как бы горька она ни была!
  WHY: reorder rhetorical exclamations into natural Russian emphasis.
- EN: You make your way into the silent, half-lit city.
  BAD: Вы входите в притихший, полутёмный город.
  GOOD: Вы углубляетесь в притихший, объятый полумраком город.
  WHY: scene movement should be spatial and atmospheric, not merely functional.
- EN: It is fear that subdues the metropolis.
  BAD: Это страх смиряет метрополию.
  GOOD: Просто страх подчинил себе этот некогда великий город.
  WHY: avoid abstract calques; recast English emphasis into Russian agency.
- EN: On your way to the palace, you may take interest in one of the following:
  BAD: На пути к дворцу вас может привлечь одно из следующего:
  GOOD: По пути к дворцу ваше внимание может привлечь одно из двух:
  WHY: gamebook option setup should be clear and idiomatic.
- EN: As you pass the beggar, he catches your gaze and says:
  BAD: Когда вы проходите мимо нищего, он ловит ваш взгляд и говорит:
  GOOD: Когда вы проходите мимо, он ловит ваш взгляд и произносит:
  WHY: avoid repeating obvious nouns and use a speech verb with narrative weight.
- EN: Ah, so there is some semblance of order in the city after all, you think.
  BAD: А, значит, в городе всё же есть некое подобие порядка, думаете вы.
  GOOD: «Что ж, хоть какое-то подобие порядка здесь сохранилось», — проносится у вас в мыслях.
  WHY: internal thoughts should read as thoughts, not literal reported syntax.
- EN: As time passes and more guards converge on the gate, you become uneasy.
  BAD: Время идёт, у ворот собирается всё больше стражников, и вы начинаете тревожиться.
  GOOD: Минуты идут, на подмогу к воротам стягиваются всё новые и новые солдаты.
        Внутри вас нарастает тревога.
  WHY: build tension through pacing and concrete movement.
- EN: the door opens with a creak
  BAD: дверь открывается со скрипом
  GOOD: створки со скрипом распахиваются
  WHY: entrance beats should use concrete scene action when Russian benefits.
- EN: she tells you in a harsh voice
  BAD: говорит она вам грубым голосом
  GOOD: слышите вы её резкий голос
  WHY: recast speech tags and voice descriptions into Russian-native narration.
- EN: Someone loses their nerve and throws the first spear.
  BAD: Кто-то не выдерживает и бросает первое копьё.
  GOOD: У кого-то сдают нервы, и в воздух летит первое копьё.
  WHY: use idiomatic Russian event phrasing for sudden action.
- EN: The stalemate devolves into a chaotic melee.
  BAD: Противостояние превращается в хаотичную схватку.
  GOOD: Напряженное ожидание мгновенно перерастает в хаотичную схватку.
  WHY: preserve the standoff collapsing into violence.
- EN: You stop your crew before too many of them fall to your blades.
  BAD: Вы останавливаете своих прежде, чем слишком многие из них падут от ваших клинков.
  GOOD: Вы осаживаете своих людей прежде, чем под вашими клинками падет слишком много местных.
  WHY: clarify pronouns in Russian; "them" means locals/guards, not your crew.
- EN: One of your company tells a joke. Not a good one, mind you.
  BAD: Кто-то из вашего отряда рассказывает шутку. Не самую удачную, надо признать.
  GOOD: Кто-то из ваших спутников отпускает шутку. Не самую остроумную, честно говоря.
  WHY: use natural narration for a comic pressure-release beat.
- EN: They do not see your mettle—nor you theirs.
  BAD: Они не видят вашей стойкости — а вы не видите их.
  GOOD: Ни вы, ни они не узнали истинной силы друг друга.
  WHY: translate the idiom's meaning, not the literal verb.
"""

_FORBIDDEN_STYLE_PHRASES = """\
FORBIDDEN STYLE PHRASES — do not emit these rejected forms:
- с великим трепетом
- обошло древний мегаполис
- Гвардия
- Но лишь немногих
- на страже стоит Стража
- Запомните «параграф
- Рогатого Города
- грубого пробуждения
- вас может привлечь одно из следующего
- убожество великолепия
- держался за смысл
- Это страх смиряет метрополию
- Они не видят вашей стойкости
- См. 0068
- звук натягиваемых тетив
"""


def build_system_prompt(
    batch: TranslationBatchV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> str:
    """Build the system prompt with terminology constraints."""
    parts = [_SYSTEM_PROMPT, _STYLE_MEMORY, _FORBIDDEN_STYLE_PHRASES]

    if concept_registry and concept_registry.concepts:
        parts.append("\nTERMINOLOGY:")
        for c in concept_registry.concepts:
            entry = (
                f"- {c.source.lemma} → {c.target.lemma}"
                f"  (allowed: {', '.join(c.target.allowed_surface_forms) or c.target.lemma})"
            )
            if c.forbidden_targets:
                entry += f"  FORBIDDEN: {', '.join(c.forbidden_targets)}"
            if c.icon_binding:
                entry += f"  [bound to icon {c.icon_binding}]"
            parts.append(entry)

    return "\n".join(parts)


def build_user_message(batch: TranslationBatchV1) -> str:
    """Build the user message containing segments to translate."""
    segments_payload = []
    segment_texts = [_inline_text(seg.source_inline) for seg in batch.segments]
    for idx, seg in enumerate(batch.segments):
        seg_dict: dict[str, object] = {
            "segment_id": seg.segment_id,
            "block_type": seg.block_type,
            "source_inline": [node.model_dump(mode="json") for node in seg.source_inline],
        }
        if seg.block_type == "narrative_group":
            seg_dict["translation_unit"] = "full_section"
            seg_dict["section_source_text"] = _section_source_text(seg.source_inline)
            seg_dict["block_boundary_contract"] = (
                "Copy every xref marker whose target_section_id starts with "
                "'translation-block:' unchanged. Translate the prose between "
                "markers as one continuous section, then keep each translated "
                "block after its corresponding marker."
            )
        source_context = {
            "prev_segment_text": segment_texts[idx - 1] if idx > 0 else "",
            "next_segment_text": segment_texts[idx + 1] if idx + 1 < len(segment_texts) else "",
        }
        if source_context["prev_segment_text"] or source_context["next_segment_text"]:
            seg_dict["source_context"] = source_context
        if _is_short_fragment(segment_texts[idx]):
            seg_dict["short_fragment_requires_context"] = True
        if seg.locked_nodes:
            seg_dict["locked_nodes"] = seg.locked_nodes
        if seg.required_concepts:
            seg_dict["required_concepts"] = seg.required_concepts
        if seg.context.prev_heading:
            seg_dict["context"] = {"prev_heading": seg.context.prev_heading}
        segments_payload.append(seg_dict)

    return json.dumps(
        {
            "batch_id": batch.batch_id,
            "source_lang": batch.source_lang,
            "target_lang": batch.target_lang,
            "segments": segments_payload,
        },
        ensure_ascii=False,
        indent=2,
    )


def _inline_text(nodes: object) -> str:
    """Return plain text from an inline-node sequence for prompt context."""
    if not isinstance(nodes, list):
        return ""
    parts: list[str] = []
    for node in nodes:
        text = getattr(node, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _section_source_text(nodes: object) -> str:
    """Return readable block-delimited text for narrative-group prompts."""
    if not isinstance(nodes, list):
        return ""
    blocks: list[str] = []
    current_label = ""
    current_parts: list[str] = []

    def flush() -> None:
        if current_label or current_parts:
            text = "".join(current_parts).strip()
            if text:
                blocks.append(f"[{current_label}]\n{text}" if current_label else text)

    for node in nodes:
        if getattr(node, "type", "") == "xref" and getattr(
            node, "target_section_id", ""
        ).startswith("translation-block:"):
            flush()
            current_label = getattr(node, "target_section_id", "").removeprefix(
                "translation-block:"
            )
            current_parts = []
            continue
        text = getattr(node, "text", None)
        if isinstance(text, str):
            current_parts.append(text)
        elif getattr(node, "type", "") == "line_break":
            current_parts.append("\n")
    flush()
    return "\n\n".join(blocks)


def _is_short_fragment(text: str) -> bool:
    """True for source snippets likely to need neighboring context."""
    words = [w for w in text.replace("—", " ").replace("-", " ").split() if w]
    return 0 < len(words) <= 5


def build_few_shot_examples() -> list[dict[str, str]]:
    """Return few-shot example pairs for translation consistency.

    Each example is a dict with "user" (source JSON) and "assistant"
    (target JSON) keys, demonstrating correct translation style, icon
    preservation, and terminology usage.
    """
    return [
        {
            "user": json.dumps(
                {
                    "batch_id": "example_1",
                    "source_lang": "en",
                    "target_lang": "ru",
                    "segments": [
                        {
                            "segment_id": "ex_heading",
                            "block_type": "heading",
                            "source_inline": [
                                {"type": "text", "text": "Battle Phase"},
                            ],
                        },
                        {
                            "segment_id": "ex_para",
                            "block_type": "paragraph",
                            "source_inline": [
                                {"type": "text", "text": "Each Argonaut has a "},
                                {"type": "text", "text": "Danger", "marks": ["bold"]},
                                {"type": "text", "text": " "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " stat on their Triskelion. When you gain ",
                                },
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i2"},
                                {"type": "text", "text": ", rotate the dial clockwise."},
                            ],
                            "locked_nodes": ["i1", "i2"],
                            "required_concepts": ["concept.danger"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "assistant": json.dumps(
                {
                    "batch_id": "example_1",
                    "segments": [
                        {
                            "segment_id": "ex_heading",
                            "target_inline": [
                                {"type": "text", "text": "Фаза Битвы"},
                            ],
                            "concept_realizations": [],
                        },
                        {
                            "segment_id": "ex_para",
                            "target_inline": [
                                {"type": "text", "text": "У каждого Аргонавта есть показатель "},
                                {"type": "text", "text": "Опасность", "marks": ["bold"]},
                                {"type": "text", "text": " "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i1"},
                                {"type": "text", "text": " на Трискелионе. Когда вы получаете "},
                                {"type": "icon", "symbol_id": "sym.danger", "instance_id": "i2"},
                                {"type": "text", "text": ", поверните диск по часовой стрелке."},
                            ],
                            "concept_realizations": [
                                {"concept_id": "concept.danger", "surface_form": "Опасность"},
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
        {
            "user": json.dumps(
                {
                    "batch_id": "example_2",
                    "source_lang": "en",
                    "target_lang": "ru",
                    "segments": [
                        {
                            "segment_id": "ex_list",
                            "block_type": "paragraph",
                            "source_inline": [
                                {"type": "text", "text": "You must gain 1 "},
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " for each die you decide to re-roll. Using ",
                                },
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i2"},
                                {"type": "text", "text": ", you can re-roll "},
                                {"type": "text", "text": "Attack Rolls", "marks": ["bold"]},
                                {"type": "text", "text": " and "},
                                {"type": "text", "text": "Evasion Rolls", "marks": ["bold"]},
                                {"type": "text", "text": "."},
                            ],
                            "locked_nodes": ["i1", "i2"],
                            "required_concepts": ["concept.fate"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "assistant": json.dumps(
                {
                    "batch_id": "example_2",
                    "segments": [
                        {
                            "segment_id": "ex_list",
                            "target_inline": [
                                {"type": "text", "text": "Вы должны получить 1 "},
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i1"},
                                {
                                    "type": "text",
                                    "text": " за каждый кубик, который вы решите "
                                    "перебросить. Используя ",
                                },
                                {"type": "icon", "symbol_id": "sym.fate", "instance_id": "i2"},
                                {"type": "text", "text": ", вы можете перебросить "},
                                {"type": "text", "text": "Броски Атаки", "marks": ["bold"]},
                                {"type": "text", "text": " и "},
                                {"type": "text", "text": "Броски Уклонения", "marks": ["bold"]},
                                {"type": "text", "text": "."},
                            ],
                            "concept_realizations": [
                                {"concept_id": "concept.fate", "surface_form": "Судьба"},
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def build_response_schema() -> dict[str, object]:
    """Return the JSON Schema that the LLM response must conform to."""
    inline_node_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "text": {"type": "string"},
            "lang": {"type": "string"},
            "marks": {"type": "array", "items": {"type": "string"}},
            "symbol_id": {"type": "string"},
            "instance_id": {"type": "string"},
            "concept_id": {"type": "string"},
            "surface_form": {"type": "string"},
            "asset_id": {"type": "string"},
            "label": {"type": "string"},
            "target_page_id": {"type": "string"},
            "target_section_id": {"type": "string"},
        },
        "required": ["type"],
        "additionalProperties": False,
    }

    concept_realization_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "concept_id": {"type": "string"},
            "surface_form": {"type": "string"},
        },
        "required": ["concept_id", "surface_form"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "batch_id": {"type": "string"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "target_inline": {
                            "type": "array",
                            "items": inline_node_schema,
                        },
                        "concept_realizations": {
                            "type": "array",
                            "items": concept_realization_schema,
                        },
                    },
                    "required": [
                        "segment_id",
                        "target_inline",
                        "concept_realizations",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["batch_id", "segments"],
        "additionalProperties": False,
    }

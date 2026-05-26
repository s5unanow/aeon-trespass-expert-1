"""Project-specific glossary, forbidden phrases, and bad/good examples.

The constants here are deliberately small and editable — the ensemble POC
(``ensemble_poc.py``) reads them once per page and embeds them into the
AGY/Opus system prompts and into the deterministic QA checks
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
    GlossaryEntry("Minoans", "минойцы", note="lowercase in running Russian prose; not 'Миносцы'"),
    GlossaryEntry("Argo", "«Арго»"),
    GlossaryEntry("Argonaut", "Аргонавт"),
    GlossaryEntry("Minotaur", "Минотавр"),
    GlossaryEntry("Daedalus Vault", "Хранилище Дедала"),
    GlossaryEntry("Horned City", "Рогатый город", note="lowercase generic noun in running prose"),
    GlossaryEntry(
        "Horned Guard",
        "Рогатая стража",
        note="archaic-Greek register; avoid Latinism 'Гвардия' and guard/guard tautologies",
    ),
    GlossaryEntry(
        "Hornsworn",
        "Рогоприсягнувшие",
        note="preserves 'sworn' connotation; do NOT conflate with 'Стража'",
    ),
    GlossaryEntry(
        "Old Priest",
        "Старый жрец",
        note="title-case only if treated as a formal card/title",
    ),
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
    "Но лишь немногих",
    "на страже стоит Стража",
    "Запомните «параграф",
    "Рогатого Города",
    "грубого пробуждения",
    "вас может привлечь одно из следующего",
    "убожество великолепия",
    "держался за смысл",
    "Это страх смиряет метрополию",
    "остатки — старые и немощные",
    "Они не видят вашей стойкости",
    "См. 0068",
    "звук натягиваемых тетив",
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
        good_ru="С замиранием сердца экипаж всматривается в приближающийся "
        "берег в поисках знаков угрозы.",
        why="'с великим трепетом' is a calque. Keep the danger-search "
        "meaning, but choose a Russian phrase with narrative tension.",
    ),
    BadGoodExample(
        en="the calamity passed by the ancient metropolis",
        bad_ru="бедствие обошло древний мегаполис",
        good_ru="беда обошла стороной древний оплот",
        why="'мегаполис' and often 'метрополия' sound modern/administrative. "
        "Prefer a mythic-literary noun when the context allows it.",
    ),
    BadGoodExample(
        en="the Horned Guard stand watch",
        bad_ru="стоит на страже Гвардия Рогатых",
        good_ru="Вход охраняет Рогатая стража.",
        why="Avoid both Latinism 'Гвардия' and tautology like 'на страже стоит Стража'.",
    ),
    BadGoodExample(
        en="Wisdom (7+) test",
        bad_ru="проверка Мудрость 7",
        good_ru="проверка Мудрости (7+)",
        why="Mechanics tokens (Wisdom (7+), Diplomacy +1/-1) must preserve "
        "parentheses, '+', and '-' verbatim.",
    ),
    BadGoodExample(
        en="So it begins",
        bad_ru="Так начинается",
        good_ru="Так берет свое начало это сказание.",
        why="A title/opening line should establish mythic storybook register, "
        "not sound like a literal UI label.",
    ),
    BadGoodExample(
        en="When darkness finally comes",
        bad_ru="Когда наконец наступает тьма",
        good_ru="Когда наконец опускается тьма",
        why="'опускается тьма' is the idiomatic Russian collocation for "
        "darkness falling in literary prose.",
    ),
    BadGoodExample(
        en="But only a few.",
        bad_ru="Но лишь немногих.",
        good_ru="Но зажглись лишь немногие из них.",
        why="Short fragments must resolve their antecedent from neighboring "
        "context. Here 'few' refers to lamps/lights, not people.",
    ),
    BadGoodExample(
        en='Note "passage 0003."',
        bad_ru="Запомните «параграф 0003».",
        good_ru="Отметьте «параграф 0003».",
        why="Gamebook 'Note passage' means record/mark it for later; it is "
        "not an instruction to memorize.",
    ),
    BadGoodExample(
        en="See 0068.",
        bad_ru="См. 0068.",
        good_ru="Перейдите к 0068.",
        why="Standalone gamebook navigation is an instruction to go to a passage, "
        "not a bibliographic cross-reference.",
    ),
    BadGoodExample(
        en="after your rude awakening",
        bad_ru="после вашего грубого пробуждения",
        good_ru="после тяжелого пробуждения",
        why="'грубое пробуждение' is a literal calque. In Russian prose, "
        "express the experience naturally rather than preserving the English adjective.",
    ),
    BadGoodExample(
        en="only embers remain",
        bad_ru="Теперь остались лишь угли.",
        good_ru="Теперь же от этого пламени остались лишь угли.",
        why="When the Russian sentence would sound abrupt, restore the implied "
        "antecedent so the image lands cleanly.",
    ),
    BadGoodExample(
        en="if the Argo is to sail the high seas again",
        bad_ru="если «Арго» вновь выйдет в открытое море",
        good_ru="если «Арго» суждено вновь выйти в открытое море",
        why="'is to' often carries fate/necessity; in mythic register, "
        "'суждено' can preserve that tone without adding facts.",
    ),
    BadGoodExample(
        en="a thing only Minos can provide",
        bad_ru="а это может предоставить лишь Минос",
        good_ru="однако открыть его может только сам Минос",
        why="Prefer concrete Russian action when the English abstract noun "
        "phrase would sound bureaucratic.",
    ),
    BadGoodExample(
        en="The engineers say",
        bad_ru="Инженеры говорят",
        good_ru="Мастера в один голос твердят",
        why="For ancient/mythic technology, 'мастера' may sound more organic "
        "than modern 'инженеры' when context allows.",
    ),
    BadGoodExample(
        en="ambrosia to sate them",
        bad_ru="амброзии, которой надобно их питать",
        good_ru="амброзии, служащей им топливом",
        why="Avoid ornate literal phrasing when a clean Russian functional "
        "rendering is more readable.",
    ),
    BadGoodExample(
        en="replacement parts only the great Daedalus Vault may contain",
        bad_ru="запасных частей, что можно найти лишь в великом Хранилище Дедала",
        good_ru="редких деталей, сокрытых в великом Хранилище Дедала",
        why="Use tighter literary compression when it preserves the meaning "
        "and avoids mechanical phrasing.",
    ),
    BadGoodExample(
        en="not having set foot on dry land for many days now",
        bad_ru="уже много дней они не ступали на твёрдую землю",
        good_ru="уже много дней они не чувствовали под ногами твердой земли",
        why="Prefer embodied Russian imagery when the source is about physical "
        "experience and restlessness.",
    ),
    BadGoodExample(
        en="a few envoys and an armed escort",
        bad_ru="несколько послов и вооружённый эскорт",
        good_ru="нескольких послов под прикрытием вооруженной охраны",
        why="For a landing party, render the tactical relationship, not a "
        "literal formal procession.",
    ),
    BadGoodExample(
        en="You hear the familiar sound of bowstrings tightening.",
        bad_ru="До вашего слуха доносится знакомый звук натягиваемых тетив.",
        good_ru="До вас доносится знакомый звук натягиваемой тетивы.",
        why="Russian normally treats this as one perceived sound/source. "
        "Plural 'натягиваемых тетив' is grammatical but clumsy; if several "
        "archers matter rhythmically, use a stronger image such as "
        "'треск натягиваемых тетив'.",
    ),
    BadGoodExample(
        en="you send an away team to a mist-shrouded key",
        bad_ru="вы отправляете высадочный отряд к окутанному туманом островку",
        good_ru="вы отправляете поисковый отряд к окутанному туманом островку",
        why="'Away team' is a function, not always a military landing unit. "
        "When the scene beat is following clues or searching, prefer "
        "'поисковый отряд' or 'разведывательный отряд'; reserve "
        "'высадочный отряд' for actual landing/assault logistics.",
    ),
    BadGoodExample(
        en="The pier is all but deserted",
        bad_ru="Пристань почти пустынна",
        good_ru="Пристань почти безлюдна",
        why="'безлюдна' is the natural word for a place with almost no people; "
        "'пустынна' can sound scenic rather than situational.",
    ),
    BadGoodExample(
        en="addressing them, like a priest of old",
        bad_ru="обращается к ним, словно жрец древних времён",
        good_ru="взывающего к ним, подобно жрецу былых веков",
        why="Elevate public speech scenes with natural literary verbs like "
        "'взывать', not generic 'обращаться'.",
    ),
    BadGoodExample(
        en="squalor of splendor",
        bad_ru="убожество великолепия",
        good_ru="нищету величия",
        why="When the English uses rhetorical contrast, choose a Russian "
        "antithesis that sounds like speech, not dictionary pairing.",
    ),
    BadGoodExample(
        en="I clung to meaning for far too long",
        bad_ru="Я слишком долго держался за смысл",
        good_ru="Я слишком долго искал во всем высший смысл",
        why="Translate the character's thought, not the preposition. The beggar "
        "sounds prophetic, so the Russian should carry that register.",
    ),
    BadGoodExample(
        en="You quicken your pace; you have no patience for raving madmen.",
        bad_ru="Вы ускоряете шаг — у вас нет терпения на бредящих безумцев.",
        good_ru="Вы прибавляете шагу — у вас нет времени на бредни сумасшедшего.",
        why="Prefer idiomatic movement and motive phrases: 'прибавляете шагу', "
        "'нет времени на бредни'.",
    ),
    BadGoodExample(
        en="Only the Truth matters, though it is bitter!",
        bad_ru="Лишь Истина имеет значение, пусть она и горька!",
        good_ru="Важна лишь Истина, как бы горька она ни была!",
        why="Reorder rhetorical exclamations into natural Russian emphasis.",
    ),
    BadGoodExample(
        en="You make your way into the silent, half-lit city.",
        bad_ru="Вы входите в притихший, полутёмный город.",
        good_ru="Вы углубляетесь в притихший, объятый полумраком город.",
        why="Scene movement should feel spatial and atmospheric, not just functional entrance.",
    ),
    BadGoodExample(
        en="It is fear that subdues the metropolis.",
        bad_ru="Это страх смиряет метрополию.",
        good_ru="Просто страх подчинил себе этот некогда великий город.",
        why="Avoid abstract calques. Recast emphatic English into a Russian "
        "sentence with clear agency and atmosphere.",
    ),
    BadGoodExample(
        en="On your way to the palace, you may take interest in one of the following:",
        bad_ru="На пути к дворцу вас может привлечь одно из следующего:",
        good_ru="По пути к дворцу ваше внимание может привлечь одно из двух:",
        why="Gamebook option setup should be clear and idiomatic; avoid "
        "mechanical 'одно из следующего'.",
    ),
    BadGoodExample(
        en="As you pass the beggar, he catches your gaze and says:",
        bad_ru="Когда вы проходите мимо нищего, он ловит ваш взгляд и говорит:",
        good_ru="Когда вы проходите мимо, он ловит ваш взгляд и произносит:",
        why="Avoid repeating the obvious noun from the previous sentence and "
        "prefer a speech verb with narrative weight.",
    ),
    BadGoodExample(
        en="Ah, so there is some semblance of order in the city after all, you think.",
        bad_ru="А, значит, в городе всё же есть некое подобие порядка, думаете вы.",
        good_ru="«Что ж, хоть какое-то подобие порядка здесь сохранилось», — "
        "проносится у вас в мыслях.",
        why="Internal thoughts should read as thoughts in Russian, not as literal reported syntax.",
    ),
    BadGoodExample(
        en="As time passes and more guards converge on the gate, you become uneasy.",
        bad_ru="Время идёт, у ворот собирается всё больше стражников, и вы начинаете тревожиться.",
        good_ru="Минуты идут, на подмогу к воротам стягиваются всё новые и "
        "новые солдаты. Внутри вас нарастает тревога.",
        why="Build tension through pacing and concrete movement; split the "
        "sentence when Russian rhythm benefits.",
    ),
    BadGoodExample(
        en="the door opens with a creak",
        bad_ru="дверь открывается со скрипом",
        good_ru="створки со скрипом распахиваются",
        why="Entrance beats should use concrete scene action when Russian benefits.",
    ),
    BadGoodExample(
        en="she tells you in a harsh voice",
        bad_ru="говорит она вам грубым голосом",
        good_ru="слышите вы её резкий голос",
        why="Recast speech tags and voice descriptions into Russian-native narration.",
    ),
    BadGoodExample(
        en="Someone loses their nerve and throws the first spear.",
        bad_ru="Кто-то не выдерживает и бросает первое копьё.",
        good_ru="У кого-то сдают нервы, и в воздух летит первое копьё.",
        why="Use idiomatic Russian event phrasing for sudden action.",
    ),
    BadGoodExample(
        en="The stalemate devolves into a chaotic melee.",
        bad_ru="Противостояние превращается в хаотичную схватку.",
        good_ru="Напряженное ожидание мгновенно перерастает в хаотичную схватку.",
        why="Preserve the scene beat: the standoff/tense wait collapses into "
        "violence, not just any 'противостояние'.",
    ),
    BadGoodExample(
        en="You stop your crew before too many of them fall to your blades.",
        bad_ru="Вы останавливаете своих прежде, чем слишком многие из них падут от ваших клинков.",
        good_ru="Вы осаживаете своих людей прежде, чем под вашими клинками "
        "падет слишком много местных.",
        why="Clarify pronoun references in Russian; 'them' means locals/guards, not your crew.",
    ),
    BadGoodExample(
        en="One of your company tells a joke. Not a good one, mind you.",
        bad_ru="Кто-то из вашего отряда рассказывает шутку. Не самую удачную, надо признать.",
        good_ru="Кто-то из ваших спутников отпускает шутку. Не самую остроумную, честно говоря.",
        why="Use natural colloquial narration for a comic pressure-release beat.",
    ),
    BadGoodExample(
        en="They do not see your mettle—nor you theirs.",
        bad_ru="Они не видят вашей стойкости — а вы не видите их.",
        good_ru="Ни вы, ни они не узнали истинной силы друг друга.",
        why="Translate the idiom's meaning; literal 'see your mettle' is weak "
        "and unclear in Russian.",
    ),
)


REVIEWER_RUBRIC: tuple[str, ...] = (
    "semantic fidelity — every English clause is preserved",
    "natural Russian — no calques or word-for-word artefacts",
    "genre/register — archaic/mythic Greek tone, not modern news/business",
    "terminology — glossary terms render consistently within and across pages",
    "mechanics preservation — passage refs, bracket placeholders, "
    "Wisdom (N+), Diplomacy +/-N kept verbatim",
    "editorial selection — when multiple variants exist, combine their best "
    "phrases; do not average them into a safer but flatter line",
    "fragment context — short fragments, pronouns, and ellipses must be "
    "translated from neighboring context, not as isolated sentences",
)

# ruff: noqa: RUF001  — Cyrillic text in translation examples is intentional.
"""Reusable Russian literary-translation style memory for LLM prompts."""

STYLE_MEMORY = """\
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
- EN: you decide to send a landing party ashore to meet the Minoans
  BAD: вы решаете отправить на берег высадочный отряд
  GOOD: вы решаете отправить на берег передовой отряд для встречи с минойцами
  WHY: choose the Russian noun by scene function. For diplomatic shore contact
       use "передовой отряд" or "отряд на берег"; for clue-search/scouting use
       "поисковый" or "разведывательный"; reserve "высадочный" for assault.
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

FORBIDDEN_STYLE_PHRASES = """\
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
- отправить на берег высадочный отряд
- вооружённый эскорт
"""

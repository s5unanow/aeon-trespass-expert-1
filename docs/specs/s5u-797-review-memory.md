# S5U-797 Review Memory

Status: candidate review memory only. Nothing in this artifact is promoted to
production prompts, deterministic QA, or the checked-in translation rule module.

Source evidence:

- `tmp/translation-eval/s5u-776-ensemble-poc/review-page-1.md`
- `tmp/translation-eval/s5u-776-ensemble-poc/memory-candidates.md`
- `scripts/translation_eval/rules.py` for already captured carry-over examples
  that S5U-797 explicitly asks to retain in the review memory.

## Linear Coverage

| Requirement | Covered by |
| --- | --- |
| Extract bad-good pairs, notes, terminology choices, collocation fixes, and prompt-rule candidates from `review-page-1.md`. | `Glossary`, `Forbidden Phrases`, `Bad-Good Examples`, and `Prompt Rules`. |
| Include examples such as `звук натягиваемых тетив` -> `звук натягиваемой тетивы` and context-sensitive alternatives for `высадочный отряд`. | `BG-031`, `BG-032`, and `PR-006`. |
| Classify each entry as glossary, forbidden phrase, bad-good example, prompt rule, or QA red flag. | Every entry below carries one of those classes. |
| A review-memory artifact exists with classified entries. | This tracked file is the artifact. |
| Each entry includes a short reason explaining the Russian prose issue. | Every table row has a `Reason` field. |
| No unreviewed rule is silently promoted to production prompts yet. | This change is documentation-only candidate memory; no prompt, QA, or rule source files are changed. |

## Glossary

| ID | Entry | Candidate Rendering | Reason |
| --- | --- | --- | --- |
| GL-001 | Argo | `«Арго»` | Ship names need Russian quotes and stable inflection-free treatment in running prose. |
| GL-002 | Knossos | `Кносс`; genitive `Кносса` | Preserves the established Greek name and avoids spelling drift. |
| GL-003 | Horned City | `Рогатый город` | The noun is generic in prose; lowercase `город` reads naturally outside a formal title. |
| GL-004 | Old Priest | `Старый жрец` | In running prose this is a role, not necessarily a title-cased proper name. |
| GL-005 | Daedalus Vault | `Хранилище Дедала` | Stable named location; avoid paraphrases that hide the game term. |
| GL-006 | Minoans | `минойцы` | Lowercase ethnonym in Russian prose; avoids awkward pseudo-proper capitalization. |
| GL-007 | Horned Guard | `Рогатая стража` | Keeps the archaic guard sense while avoiding the modern Latinism `гвардия`. |
| GL-008 | Hornsworn | `Рогоприсягнувшие` | Preserves the oath component and keeps the faction distinct from the Guard. |
| GL-009 | Phaedra | `Федра` | Standard Russian rendering of the mythic name. |
| GL-010 | Minos | `Минос`; genitive `Миноса` | Stable mythic proper name; used in both narrative and mechanics. |
| GL-011 | Androgeos | `Андрогей` | Standard mythic proper-name rendering; avoids English transliteration drift. |
| GL-012 | Wisdom / Diplomacy | `Мудрость` / `Дипломатия` | Mechanics labels must stay stable and preserve numeric modifiers. |
| GL-013 | aeolipile engines | `эолипильные двигатели` | Keeps the technical fantasy term; prose around it may use `мастера` instead of modern `инженеры`. |

## Forbidden Phrases

| ID | Phrase | Reason |
| --- | --- | --- |
| FP-001 | `Так начинается` | Too literal for an opening title; sounds like a UI label rather than mythic narration. |
| FP-002 | `с великим трепетом` | Calque of `with great trepidation`; Russian literary prose prefers an idiom such as `с замиранием сердца`. |
| FP-003 | `Рогатого Города` | Over-capitalizes a generic noun in running Russian prose. |
| FP-004 | `грубого пробуждения` | Literal calque; `грубое пробуждение` is unnatural for a hard awakening. |
| FP-005 | `Но лишь немногих` | Mistranslates the fragment because the antecedent is lamps/lights, not people. |
| FP-006 | `высадочный отряд` | Overly military when the scene needs envoys, scouting, search, or shore party nuance. |
| FP-007 | `вооружённый эскорт` | Sounds like a formal procession; the scene needs protection or cover. |
| FP-008 | `Пристань почти пустынна` | `пустынна` is scenic; `безлюдна` is the natural word for almost no people. |
| FP-009 | `убожество великолепия` | Dictionary-pair antithesis; too stiff for prophetic speech. |
| FP-010 | `держался за смысл` | Literal preposition mapping; Russian should express seeking higher meaning. |
| FP-011 | `бредящих безумцев` | Overwrought and awkward plural; the beat refers to one raving madman. |
| FP-012 | `Это страх смиряет метрополию` | Abstract English syntax plus modern `метрополия`; weak in mythic prose. |
| FP-013 | `вас может привлечь одно из следующего` | Mechanical option setup; not idiomatic Russian gamebook prose. |
| FP-014 | `Запомните «параграф` | Gamebook `Note passage` means mark or record it, not memorize it. |
| FP-015 | `на страже стоит Стража Рогатых` | Tautological and terminologically wrong for `Horned Guard`. |
| FP-016 | `А, значит, ... думаете вы` | Literal reported-thought syntax; Russian internal thought should be recast. |
| FP-017 | `Время идёт, у ворот собирается` | Flat summary where the scene needs mounting tension and movement. |
| FP-018 | `остатки — старые и немощные` | Abstract noun plus adjectives reads like inventory, not a scene of decrepit guards. |
| FP-019 | `Они не видят вашей стойкости` | Literal `mettle` rendering is unclear and weak in Russian. |
| FP-020 | `См. 0068` | Bibliographic shorthand; gamebook navigation should be an imperative. |
| FP-021 | `звук натягиваемых тетив` | Grammatical but clumsy plural collocation; Russian hears one familiar sound unless the plurality is foregrounded. |

## Bad-Good Examples

| ID | Source | Bad | Good | Reason |
| --- | --- | --- | --- | --- |
| BG-001 | So it begins | `Так начинается` | `Так берет свое начало это сказание.` | Opens in a mythic register instead of sounding like a literal heading. |
| BG-002 | The Argo cuts through the evening waves | `«Арго» режет вечерние волны.` | `«Арго» рассекает вечерние волны.` | `Рассекает` is the natural literary verb for a ship cleaving water. |
| BG-003 | With great trepidation | `С большой тревогой команда наблюдает за береговой линией` | `С замиранием сердца экипаж всматривается в приближающийся берег` | Converts a literal anxiety phrase into tense Russian narration. |
| BG-004 | ancient metropolis | `древнюю метрополию` | `древний оплот` | Avoids a modern administrative noun in mythic-fantasy prose. |
| BG-005 | When darkness finally comes | `Когда наконец наступает тьма` | `Когда наконец опускается тьма` | Uses the idiomatic Russian collocation for falling darkness. |
| BG-006 | But only a few. | `Но лишь немногих.` | `Но зажглись лишь немногие из них.` | Resolves the fragment from context; `few` refers to lamps. |
| BG-007 | after your rude awakening | `после вашего грубого пробуждения` | `после тяжелого пробуждения` | Keeps the experience without calquing `rude`. |
| BG-008 | if the Argo is to sail | `если «Арго» вновь выйдет` | `если «Арго» суждено вновь выйти` | Preserves the fate/necessity shade of `is to` in genre register. |
| BG-009 | a thing only Minos can provide | `это может предоставить лишь Минос` | `открыть его может только сам Минос` | Replaces abstract bureaucratic phrasing with concrete action. |
| BG-010 | The engineers say | `Инженеры говорят` | `Мастера в один голос твердят` | Ancient/fantasy technical context often reads better with `мастера`. |
| BG-011 | ambrosia to sate them | `амброзии, которой надобно их питать` | `амброзии, служащей им топливом` | Cleaner functional Russian beats ornate literalism. |
| BG-012 | replacement parts | `запасных частей` | `редких деталей` | Tighter prose preserves meaning without mechanical phrasing. |
| BG-013 | not set foot on dry land | `не ступали на твёрдую землю` | `не чувствовали под ногами твердой земли` | Embodied imagery better explains the Titans' restlessness. |
| BG-014 | landing party | `высадочный отряд` | `передовой отряд` | The paragraph describes envoys under guard, not a military landing action. |
| BG-015 | armed escort | `вооружённый эскорт` | `под прикрытием вооруженной охраны` | Renders tactical protection rather than ceremonial escort. |
| BG-016 | The pier is all but deserted | `Пристань почти пустынна` | `Пристань почти безлюдна` | `Безлюдна` is the natural people-count adjective. |
| BG-017 | addressing them | `обращается к ним` | `взывающего к ним` | Public prophetic speech needs a stronger Russian verb. |
| BG-018 | squalor of splendor | `убожество великолепия` | `нищету величия` | Keeps the antithesis while sounding speakable. |
| BG-019 | clung to meaning | `держался за смысл` | `искал во всем высший смысл` | Translates the character's thought rather than the English preposition. |
| BG-020 | quicken your pace | `Вы ускоряете шаг` | `Вы прибавляете шагу` | Uses the idiomatic Russian movement phrase. |
| BG-021 | no patience for raving madmen | `нет терпения на бредящих безумцев` | `нет времени на бредни сумасшедшего` | More natural motive and number in context. |
| BG-022 | Only the Truth matters | `Лишь Истина имеет значение` | `Важна лишь Истина` | Natural Russian emphasis for a rhetorical exclamation. |
| BG-023 | make your way into the city | `Вы входите в город` | `Вы углубляетесь в город` | Gives spatial progression and atmosphere. |
| BG-024 | half-lit city | `полутёмный город` | `объятый полумраком город` | More literary atmosphere without changing meaning. |
| BG-025 | It is fear that subdues | `Это страх смиряет метрополию` | `Страх подчинил себе этот некогда великий город` | Recasts emphatic English into clear Russian agency. |
| BG-026 | take interest in one of the following | `вас может привлечь одно из следующего` | `ваше внимание может привлечь одно из двух` | Idiomatic option setup with the correct number of choices. |
| BG-027 | Note "passage 0003." | `Запомните «параграф 0003».` | `Отметьте «параграф 0003».` | Gamebook state tracking means mark the passage for later. |
| BG-028 | Horned Guard stand watch | `на страже стоит Стража Рогатых` | `Вход охраняет Рогатая стража.` | Avoids tautology and keeps the canonical faction term. |
| BG-029 | some semblance of order | `есть некое подобие порядка, думаете вы` | `«Что ж, хоть какое-то подобие порядка здесь сохранилось», — проносится у вас в мыслях.` | Internal thought should read as thought, not literal reported syntax. |
| BG-030 | more guards converge | `у ворот собирается всё больше стражников` | `на подмогу к воротам стягиваются всё новые и новые солдаты` | Builds tension through movement and reinforcement. |
| BG-031 | bowstrings tightening | `звук натягиваемых тетив` | `звук натягиваемой тетивы` | Treats the perception as one familiar sound; plural is only useful when several bowstrings are narratively important. |
| BG-032 | away team / landing party | `высадочный отряд` | `поисковый отряд`, `разведывательный отряд`, `передовой отряд`, or `отряд на берег` | The Russian term must follow the scene function: search, scouting, diplomatic contact, or actual landing. |
| BG-033 | someone loses their nerve | `Кто-то не выдерживает и бросает первое копьё.` | `У кого-то сдают нервы, и в воздух летит первое копьё.` | Idiomatic Russian event phrasing makes the sudden action sharper. |
| BG-034 | stalemate devolves | `Противостояние превращается в хаотичную схватку.` | `Напряженное ожидание мгновенно перерастает в хаотичную схватку.` | Preserves the beat of tense waiting collapsing into violence. |
| BG-035 | too many of them fall | `слишком многие из них падут от ваших клинков` | `под вашими клинками падет слишком много местных` | Clarifies that `them` means locals/guards, not the player's crew. |
| BG-036 | tells a joke | `рассказывает шутку` | `отпускает шутку` | More natural Russian for a quick pressure-release joke. |
| BG-037 | Not a good one | `Не самую удачную, надо признать` | `Не самую остроумную, честно говоря` | Keeps the lightly comic narrator voice. |
| BG-038 | They do not see your mettle | `Они не видят вашей стойкости` | `Ни вы, ни они не узнали истинной силы друг друга.` | Translates the idiom's meaning instead of its surface image. |
| BG-039 | gate opens with a creak | `Ворота открываются со скрипом` | `Ворота со скрипом распахиваются` | Stronger concrete action for an entrance beat. |
| BG-040 | she holds a torch in her hand | `В руке она держит факел` | `с факелом в руке` | Compresses a redundant body-part construction. |
| BG-041 | tells you in a soft voice | `говорит она мягким голосом` | `слышите вы её мягкий голос` | Recasts the speech tag into Russian-native narration. |
| BG-042 | See 0068. | `См. 0068.` | `Перейдите к 0068.` | Navigation should be an instruction, not a citation. |

## Prompt Rules

| ID | Rule | Reason |
| --- | --- | --- |
| PR-001 | Translate fragments against neighboring context before choosing grammar or number. | Prevents errors like `Но лишь немногих`, where the isolated fragment hides the lamp antecedent. |
| PR-002 | Prefer mythic, embodied Russian prose over modern administrative abstractions. | Avoids `метрополия`, `предоставить доступ`, and similar register breaks. |
| PR-003 | Recast internal thought, speech tags, and rhetorical exclamations into native Russian syntax. | Literal English reporting order sounds stiff and weakens character voice. |
| PR-004 | Preserve game mechanics exactly: passage IDs, `Note passage`, `See NNNN`, stat names, parentheses, plus and minus modifiers. | These are executable gamebook instructions and state changes, not decorative prose. |
| PR-005 | Split or recombine sentences when Russian rhythm needs it, while preserving every source clause. | Tension beats often improve when a long English sentence becomes two Russian sentences. |
| PR-006 | Treat team/party terms as scene functions, not fixed military labels. | `Landing party` / `away team` may be diplomatic, scouting, search, or assault depending on context. |
| PR-007 | Use stronger Russian scene verbs for public address, movement, and entrances. | Verbs such as `взывать`, `углубляться`, and `распахиваться` carry narrative weight that generic verbs lose. |
| PR-008 | Do not promote reviewer rewrites blindly; normalize obvious typos before reuse. | Review comments include typos such as `произонсит`, `бору`, and `переростает`; the memory should preserve the lesson, not the typo. |

## QA Red Flags

| ID | Red Flag | Reason |
| --- | --- | --- |
| QA-001 | Forbidden phrase appears verbatim in a candidate translation. | These are known outputs that produced unnatural or incorrect Russian. |
| QA-002 | A short fragment translates without an explicit antecedent from adjacent text. | Fragment mistranslation is hard for deterministic QA but high-impact in gamebook prose. |
| QA-003 | Modern register terms appear in mythic narration: `метрополия`, bureaucratic `предоставить`, ceremonial `эскорт` where tactical cover is meant. | These words can be accurate in isolation but break genre tone. |
| QA-004 | Mechanics instructions use citation wording (`См.`) or memory wording (`Запомните`) for gamebook state/navigation. | The player needs an action instruction, not a bibliographic or cognitive instruction. |
| QA-005 | `Гвардия` or guard/guard tautologies appear near Horned Guard. | The canonical faction rendering is `Рогатая стража`, and tautologies read poorly. |
| QA-006 | `высадочный отряд` appears without a landing/assault context. | It may be wrong when the scene is search, scouting, shore contact, or diplomacy. |
| QA-007 | `звук натягиваемых тетив` appears. | The plural collocation is an observed clumsy output; prefer singular perceived sound or a stronger plural image. |
| QA-008 | Repeated flat openers such as `Вы`, `Когда`, `Но`, `Это` drive consecutive sentences. | The review repeatedly fixes pacing by varying openings and recasting syntax. |
| QA-009 | Literal pronoun mapping leaves ambiguous `them`, `their`, or omitted nouns. | Russian often needs the noun restored to avoid reversing who acts or suffers. |

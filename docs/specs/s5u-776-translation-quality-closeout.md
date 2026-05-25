# S5U-776 Translation Quality Closeout

S5U-776 is closed as the original local-only ensemble translation POC. Do not
continue expanding that issue. Use the follow-up Linear sequence S5U-796 through
S5U-803 for calibration, rule promotion, style QA, and full-pipeline rollout.

## Local Evidence

The raw evidence remains local and gitignored under:

```text
tmp/translation-eval/s5u-776-ensemble-poc/
```

Important artifacts:

- `inputs/page-{1,2}-en.txt` — source pages used for the POC.
- `agy/page-{1,2}-*.txt` — AGY / Antigravity 3-variant drafts.
- `sonnet/page-{1,2}-*.txt` — older Sonnet 3-variant drafts kept for comparison.
- `opus/page-{1,2}-synth-v{1,2}.txt` — original synthesis/editor outputs.
- `codex/page-{1,2}-synth-v{1,2}.txt` — Codex 5.5 high synthesis/editor outputs.
- `qa/` and `codex/qa/` — deterministic QA output, currently insufficient for
  native Russian prose quality.
- `review-page-1.md` — human comments and best available calibration signal.
- `review-page-1-agy-refined.md` — AGY-refined review notes.
- `review-page-2.md` — second-page review scaffold.
- `memory-candidates.md` — extracted glossary, forbidden phrase, and bad→good
  candidates.
- `report.md` and `codex/report.md` — historical run summaries.

Additional local comparison evidence exists under:

```text
tmp/translation-eval/give-me-original-text-now/
```

That folder contains AGY, Codex, all-Codex, Gemini phone-app, and
Codex+Gemini comparison runs for the later DOCX sample. Those files are useful
for qualitative comparison, but S5U-776 remains the calibration set because it
contains explicit human review comments.

## What Was Learned

The AGY + Codex baseline is structurally viable: it preserves references,
mechanics, and terminology better than a raw single-shot translation. However,
deterministic QA can report zero findings while the Russian still reads like a
translation.

Observed failure class:

- Awkward but grammatical collocations, e.g. `звук натягиваемых тетив` instead
  of `звук натягиваемой тетивы` or an atmospheric equivalent.
- Context-insensitive terms, e.g. overusing `высадочный отряд` where the scene
  function may require `поисковый отряд`, `разведывательный отряд`, or simply
  `отряд на берег`.
- Hard-stop pacing and repeated openers such as `Вы`, `И`, `Но`, `Затем`,
  `Это`, `Когда`.
- Literal English syntax that is accurate but stiff in Russian.
- Modern administrative register in mythic-fantasy prose.

## Durable Work Already Promoted

The current follow-up branch promotes the most valuable S5U-776 lessons into
tracked code:

- `scripts/translation_eval/rules.py` now carries expanded glossary entries,
  forbidden phrases, and bad→good examples.
- `scripts/translation_eval/prompts.py` and
  `apps/pipeline/src/atr_pipeline/services/llm/prompt_builder.py` carry stronger
  Russian literary style guidance.
- `scripts/translation_eval/qa_checks.py` contains initial style red flags
  learned from review.
- `apps/pipeline/src/atr_pipeline/stages/translation/grouping.py` plus planner,
  stage, and validator changes support grouped narrative translation units with
  boundary-marker validation.
- `apps/pipeline/src/atr_pipeline/services/llm/agy_cli_adapter.py` adds the
  experimental AGY CLI provider surface.

## Follow-Up Boundary

S5U-796 is the next execution boundary:

1. Freeze S5U-776 as a calibration benchmark.
2. Finish extracting `review-page-1.md` into structured review memory.
3. Promote only accepted memory into prompts/rules/QA.
4. Add Russian style QA and monolingual critic/repair stages.
5. Re-run S5U-776 into a new non-destructive folder.
6. Only after 776 passes, apply the stabilized pipeline to the DOCX sample and
   larger translation flow.

Do not overwrite the existing 776 artifacts. New calibration runs should use a
new subfolder such as:

```text
tmp/translation-eval/s5u-776-ensemble-poc/style-v2/
```

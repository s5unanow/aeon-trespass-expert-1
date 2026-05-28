# S5U-803 Translation Quality Rollout

Status: completed local DOCX rollout. Output is generated under:

```text
tmp/translation-eval/give-me-original-text-now/s5u-803-stabilized/
```

The source DOCX remains outside the repo at:

```text
/Users/s5una/Downloads/Give me original text now.docx
```

The runner consumes the extracted source text:

```text
tmp/translation-eval/give-me-original-text-now/inputs/source-en-clean.txt
```

## S5U-776 / S5U-802 Review

The S5U-802 rerun produced all required calibration artifacts, but it did not
beat the human-reviewed S5U-776 baseline overall. Page 1 had 11 paragraphs
classified as regressed away from the human target, and the tracked closeout
therefore treats `style-v2/` as calibration evidence rather than a promoted
translation baseline.

Noisy or over-aggressive surfaces identified from that review:

- The old 3-in-5 cadence window flagged normal second-person gamebook prose too
  early.
- Short-sentence clustering had the same 3-in-5 sensitivity and no separate
  sustained hard-stop ratio.
- The `обращается к ним` collocation flag was too broad; the review memory only
  justifies it for public prophetic/priestly address contexts.
- The `высадочный отряд` flag was too broad; it should focus on shore-contact
  / diplomatic scenes, not every literal landing-party mention.
- Codex critic `info` findings are useful review notes, but S5U-802 showed they
  are too noisy to feed into automatic paragraph repair.

## Stabilized Thresholds

| Surface | S5U-803 threshold | Rationale |
| -- | -- | -- |
| Repeated hard openers (`Вы`, `И`, `Но`, `Затем`, `Это`, `Когда`) | 4 hits within 6 non-mechanics prose sentences | Keeps the signal for dense cadence failure while allowing ordinary gamebook second-person narration. |
| Repeated `Вы + verb` starts | 4 hits within 6 non-mechanics prose sentences | Same threshold as hard openers because this is a rhythm smell, not a mechanics error. |
| Short sentence cluster | 4 sentences of 4 words or fewer within 6 non-mechanics prose sentences | Avoids flagging a few legitimate clipped beats while still catching visibly chopped prose. |
| Hard-stop ratio | At least 60% short prose sentences, minimum 6 prose sentences | Catches sustained choppiness even when it is not localized to one exact window. |
| `обращается к ним` | Flag only when the same sentence frames the address as `словно/подобно жрец` | Generic addressing can be correct Russian; the bad S5U-776 pattern was prophetic/priestly flatness. |
| `высадочный отряд` | Flag only with shore-contact context such as `на берег`, `для встречи`, `минойц`, or envoys | Legitimate landing logistics should not be auto-repaired; diplomatic shore-contact scenes need scene-function wording. |
| Codex critic severity | Auto-repair `warning` and above; keep `info` as review-only | Prevents optional style taste from rewriting accepted human targets. |

Hard preservation checks did not change: passage refs, placeholders, mechanics
tokens, glossary misses, forbidden phrases, and omission witness checks retain
their prior behavior.

## Final Stage Order

The S5U-803 DOCX runner is:

```text
DOCX extracted EN source
-> 3 Codex translation variants
-> Codex synthesis
-> deterministic QA/style QA
-> Codex editor
-> Codex JSON style critic
-> targeted paragraph repair
-> final deterministic QA/style QA
```

Command:

```bash
uv run python -m scripts.translation_eval.docx_rollout
```

Optional Gemini style reference:

```bash
uv run python -m scripts.translation_eval.docx_rollout \
  --style-reference tmp/translation-eval/give-me-original-text-now/gemini/synth-v2.txt
```

The style reference is advisory only. The prompt tells Codex to borrow Russian
rhythm ideas only when they preserve source meaning and pipeline structure, and
not to copy Gemini's reordered blocks, mechanics errors, or terminology drift.
The runner accepts style-reference paths only under the DOCX scratch root.

## Model Roles

| Role | Default model/path | Purpose |
| -- | -- | -- |
| Codex variants | `gpt-5.5`, high reasoning | Generate literal-fidelity, literary-prose, and idiomatic-natural drafts. |
| Codex synthesis | `gpt-5.5`, high reasoning | Select the best phrasing from variants without averaging them. |
| Deterministic QA/style QA | `scripts/translation_eval/qa_checks.py` and `style_qa.py` | Catch hard preservation errors and high-confidence prose smells. |
| Codex editor | `gpt-5.5`, high reasoning | Resolve deterministic findings and polish the synthesized draft. |
| Codex style critic | `atr_pipeline.services.llm.russian_style_critic_codex` | Produce structured monolingual style findings. |
| Codex targeted repair | `atr_pipeline.services.llm.russian_style_repair_codex` | Repair only paragraphs with warning-or-higher critic findings. |

Prompt and rule sources:

- `scripts/translation_eval/prompts.py`
- `scripts/translation_eval/rules.py`
- `scripts/translation_eval/style_qa.py`
- `apps/pipeline/src/atr_pipeline/services/llm/russian_style_critic*.py`
- `apps/pipeline/src/atr_pipeline/services/llm/russian_style_repair*.py`

## Output Folders

- S5U-776 original POC: `tmp/translation-eval/s5u-776-ensemble-poc/`
- S5U-802 calibration rerun: `tmp/translation-eval/s5u-776-ensemble-poc/style-v2/`
- Earlier DOCX comparisons: `tmp/translation-eval/give-me-original-text-now/{agy,codex,codex3,codex-gemini,gemini}/`
- S5U-803 stabilized DOCX rollout: `tmp/translation-eval/give-me-original-text-now/s5u-803-stabilized/`

The S5U-803 runner rejects the DOCX scratch root itself and paths outside that
root, so it cannot write into tracked corpus/export paths by default. Optional
style-reference reads are likewise constrained to the DOCX scratch root.

Expected S5U-803 artifact inventory:

- `inputs/source-en-clean.txt`
- `variants/{literal-fidelity,literary-prose,idiomatic-natural}.txt`
- `synthesis/synth-v1.txt`
- `editor/editor.txt`
- `final/synth-v2.txt`
- `qa/qa-{v1,editor,final}.json`
- `critic/critic.json`
- `repair/repair-report.json`
- `report.md`

## Local Run Result

Command:

```bash
uv run python -m scripts.translation_eval.docx_rollout
```

Run summary from `s5u-803-stabilized/report.md`:

| QA v1 | QA editor | Critic findings | Repaired paragraphs | QA final | Wall (s) | Tokens |
| --: | --: | --: | --: | --: | --: | --: |
| 1 | 0 | 22 | 19 | 0 | 571.3 | 198838 |

The single v1 finding was the known bowstring collocation. The editor/critic
and targeted repair stages resolved deterministic QA/style findings to zero in
`qa/qa-final.json`.

## Review Workflow

1. Read `report.md` for QA counts, repaired paragraphs, timings, and token use.
2. Inspect `qa/qa-final.json`; any deterministic finding is a manual review
   blocker unless explicitly waived in the PR body.
3. Inspect `repair/repair-report.json`; confirm each warning-or-higher repair
   preserves source meaning and does not rewrite accepted style unnecessarily.
4. Spot-check `final/synth-v2.txt` against `inputs/source-en-clean.txt`, with
   special attention to mechanics, paragraph order, option blocks, and
   diplomacy/resource lines.
5. Treat `critic/critic.json` `info` findings as review notes only. They are
   intentionally not automatic repair inputs after S5U-802.

## When To Use Each Path

| Path | Use when | Do not use when |
| -- | -- | -- |
| AGY-only | Quick exploratory drafts, low-cost style variety, or when Codex/Anthropic are unavailable. | Shipping user-facing final text without a separate QA/editor pass. |
| AGY + Codex | Strong default for mixed local/higher-quality runs: AGY produces variety, Codex synthesizes/edits/repairs. | The AGY session/model profile cannot be controlled or the source contains sensitive material that should not leave the chosen provider path. |
| All-Codex S5U-803 runner | Reproducible local rollout with one provider surface and structured critic/repair artifacts. | Cases needing AGY's stylistic diversity as a deliberate input. |
| Optional Gemini style reference | A human wants to borrow cadence ideas from an existing Gemini draft while keeping Codex as the authoritative editor. | The Gemini draft has structural reordering, mechanics drift, or terminology errors that would distract the editor. |

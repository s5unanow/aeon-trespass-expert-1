# scripts/translation_eval — S5U-776 ensemble translation POC

Local-only proof of concept for the staged EN→RU translation workflow:

```
EN → AGY 3 variants → Opus literary synthesis → automated QA →
TranslateGemma omission witness → Opus final editor → human spot review
```

This is not in the production pipeline path. The orchestrator runs over the
two-page sample shipped in `tmp/translation-eval/` (S5U-775 baseline) and
writes all artefacts under `tmp/translation-eval/s5u-776-ensemble-poc/`,
which is gitignored — outputs stay on the local machine.

S5U-776 is closed as the original POC. For the closeout inventory and the
follow-up boundary, see
`docs/specs/s5u-776-translation-quality-closeout.md`. New calibration runs
should write to a new non-destructive subfolder such as
`tmp/translation-eval/s5u-776-ensemble-poc/style-v2/`.

## Layout

```
scripts/translation_eval/
  rules.py               # glossary, forbidden phrases, bad/good examples
  qa_checks.py           # deterministic QA functions (pure, unit-tested)
  prompts.py             # AGY variant + Opus synthesis/final-editor prompts
  ensemble_poc.py        # CLI orchestrator
  improved_rerun.py      # S5U-802 Codex rerun + critic/repair artifacts
  docx_rollout.py        # S5U-803 stabilized DOCX sample rollout
```

## Run

The orchestrator needs:

- `agy` on PATH for the three variant drafts.
- `ANTHROPIC_API_KEY` and the `anthropic` SDK for Opus synthesis/final editing.

AGY CLI v1 exposes `--print` / `--print-timeout`, but no non-interactive
model-selection flag in `agy --help`. The runner records and requests the
desired `Pro` + `high` profile in the prompt; the actual model must be selected
in the user's Antigravity CLI/session configuration until AGY exposes a flag.

```bash
ANTHROPIC_API_KEY=... uv run python -m scripts.translation_eval.ensemble_poc 1 2
```

Use `--opus-model` or `ANTHROPIC_OPUS_MODEL` to override the default
documented Anthropic model snapshot.

Output (gitignored):

```
tmp/translation-eval/s5u-776-ensemble-poc/
  inputs/    page-{1,2}-en.txt        (copied for self-containment)
  agy/       page-{1,2}-{lens}.txt    (literal-fidelity / literary-prose / idiomatic-natural)
  opus/      page-{1,2}-synth-v1.txt  (Opus synthesis)
  opus/      page-{1,2}-synth-v2.txt  (Opus final editor output)
  qa/        page-{1,2}-qa-v{1,2}.json (QAFinding records)
  report.md
  memory-candidates.md
```

## S5U-802 improved rerun

S5U-802 reruns the S5U-776 calibration sample through the promoted rules,
deterministic style QA, Codex style critic, and targeted paragraph repair.
It is Codex CLI backed and writes a new non-destructive subfolder:

```bash
uv run python -m scripts.translation_eval.improved_rerun 1 2
```

Output (gitignored):

```text
tmp/translation-eval/s5u-776-ensemble-poc/style-v2/
  final/page-{1,2}-ru-final.txt
  qa/page-{1,2}-qa-{v1,editor,final}.json
  critic/page-{1,2}-critic.json
  repair/page-{1,2}-repair-report.json
  report.md
  comparison.md
```

## S5U-803 DOCX rollout

S5U-803 applies the stabilized all-Codex pipeline to the extracted DOCX sample
under `tmp/translation-eval/give-me-original-text-now/inputs/source-en-clean.txt`.
It writes a new non-destructive local artifact folder:

```bash
uv run python -m scripts.translation_eval.docx_rollout
```

Output (gitignored):

```text
tmp/translation-eval/give-me-original-text-now/s5u-803-stabilized/
  inputs/source-en-clean.txt
  variants/{literal-fidelity,literary-prose,idiomatic-natural}.txt
  synthesis/synth-v1.txt
  editor/editor.txt
  final/synth-v2.txt
  qa/qa-{v1,editor,final}.json
  critic/critic.json
  repair/repair-report.json
  report.md
```

Use `--style-reference tmp/translation-eval/give-me-original-text-now/gemini/synth-v2.txt`
only when Gemini should serve as an advisory Russian rhythm reference. The
Codex editor remains authoritative for source structure, mechanics, and
terminology. Full threshold rationale and workflow guidance live in
`docs/specs/s5u-803-translation-quality-rollout.md`.

## TranslateGemma omission witness

The orchestrator reads the existing
`tmp/translation-eval/page-{1,2}-ru-translategemma.txt` produced by S5U-775
to run the coarse paragraph/character coverage check against the Opus
synthesis. If the file is missing, the omission check is skipped (the
other five checks still run).

To regenerate the witness:

```bash
HF_HOME="$HOME/Models/huggingface" \
  uv run --no-project --with "transformers>=4.46" --with torch \
  --with accelerate --with sentencepiece --with protobuf \
  python tmp/translation-eval/run_translategemma.py 1
```

## Running just the QA checks (unit tests)

```bash
uv run pytest apps/pipeline/tests/unit/test_translation_eval_qa_checks.py
```

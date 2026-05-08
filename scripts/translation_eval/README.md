# scripts/translation_eval — S5U-776 ensemble translation POC

Local-only proof of concept for the staged EN→RU translation workflow:

```
EN → Sonnet 3 variants → Opus literary synthesis → automated QA →
TranslateGemma omission witness → Opus minimal repair → human spot review
```

This is not in the production pipeline path. The orchestrator runs over the
two-page sample shipped in `tmp/translation-eval/` (S5U-775 baseline) and
writes all artefacts under `tmp/translation-eval/s5u-776-ensemble-poc/`,
which is gitignored — outputs stay on the local machine.

## Layout

```
scripts/translation_eval/
  rules.py               # glossary, forbidden phrases, bad/good examples
  qa_checks.py           # deterministic QA functions (pure, unit-tested)
  prompts.py             # Sonnet variant + Opus synthesis/repair prompts
  ensemble_poc.py        # CLI orchestrator
```

## Run

The orchestrator needs `ANTHROPIC_API_KEY` and the `anthropic` SDK (already
on the apps/pipeline dependency tree).

```bash
ANTHROPIC_API_KEY=... uv run python scripts/translation_eval/ensemble_poc.py 1 2
```

Output (gitignored):

```
tmp/translation-eval/s5u-776-ensemble-poc/
  inputs/    page-{1,2}-en.txt        (copied for self-containment)
  sonnet/    page-{1,2}-{lens}.txt    (literal-fidelity / literary-prose / idiomatic-natural)
  opus/      page-{1,2}-synth-v1.txt  (Opus synthesis)
  opus/      page-{1,2}-synth-v2.txt  (Opus minimal repair, only if v1 had findings)
  qa/        page-{1,2}-qa-v{1,2}.json (QAFinding records)
  report.md
  memory-candidates.md
```

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

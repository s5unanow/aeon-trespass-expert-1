# Local MT model characterization (S5U-774)

Smoke-test results for three local EN→RU machine-translation candidates,
captured before any pipeline integration work begins. Feeds the go/no-go
decisions in S5U-768 (runtime adapters), S5U-769 (corpus benchmark), and
S5U-771 (final candidate selection).

## Host

Apple M4 Max, 14 cores (10P + 4E), **36 GB unified memory**, macOS Darwin
25.4.0. Runtime: Hugging Face `transformers` ≥ 4.46 with PyTorch on the
`mps` device, `bfloat16` weights for all three. Models cached under
`HF_HOME=~/Models/huggingface` per `local-models-cache.md`.

Each model was loaded in a fresh Python process so the OS reclaimed
weights between runs. Disk size sums the HF `blobs/` directory only
(snapshot symlinks point at the same blobs and would double-count).
Tokens/sec is measured on a fixed 60-token EN sample after one warm-up
generation; peak resident memory is `ru_maxrss` for the process.

## Sample prompt (fixed across all three runs)

> The Argonaut suffers 3 damage and gains a Survival token. If a
> Primordial moves into their hex, they may spend 1 Insight to perform
> a Reaction attack. After resolving combat, return all spent dice to
> the bag and check the Encounter status.

Three sentences, board-game-flavoured terminology, ~50 words / ~70
tokens — representative of an Aeon Trespass rulebook paragraph.

## Results

| Model                                 | Disk    | Load   | Peak RSS | Output tok/s | Sentences  | Verdict |
|---------------------------------------|---------|--------|----------|--------------|------------|---------|
| `facebook/nllb-200-3.3B`              | 16.4 GB | 30 s   | 26.1 GB  | **42**       | 2 / 3      | Loads + runs; **drops first sentence**; recall risk |
| `google/madlad400-10b-mt`             | 39.9 GB | 47 s   | 17.6 GB  | **19**       | 2 / 3      | Loads + runs; **drops first sentence**; recall risk |
| `google/translategemma-12b-it`        | 22.7 GB | 92 s   | 20.9 GB  | **11**       | **3 / 3**  | Loads + runs; only candidate that translated all three sentences |

All three loaded inside the 36 GB envelope. Peak RSS on macOS includes
mmap'd weight pages, so the column reflects what `ps`/Activity Monitor
will show, not the strict working set; expect ~40-60% of column value
under steady-state inference.

### Sample EN→RU outputs

NLLB-200 3.3B:

> *Если Первобытный перемещается в их проклятие, они могут потратить
> 1 Прозрение, чтобы выполнить атаку Реакции. После разрешения боя
> верните все потраченные кости в мешок и проверьте статус Встречи.*

MADLAD-400 10B:

> *Если Первобытный переместится в их шестигранник, они могут потратить
> 1 очко Проницательности на выполнение атаки Реакции. После разрешения
> сражения верните все потраченные кости в мешок и проверьте статус
> Встречи.*

TranslateGemma 12B-it:

> *Корабль "Аргонавт" получает 3 единицы урона и получает жетон
> "Выживание". Если существо из числа Первобытных перемещается в
> соседнюю клетку, игрок может потратить 1 очко "Прозрения", чтобы
> совершить контратаку. После разрешения боевого столкновения, все
> использованные кубики возвращаются в мешок, и проверяется статус
> "Встречи".*

### Quality observations (single-sample, not a benchmark)

- **NLLB and MADLAD silently drop the first sentence** ("The Argonaut
  suffers 3 damage…") on this multi-sentence input — they hit EOS at 60
  / 63 output tokens despite `max_new_tokens=160`. This is a known
  pattern with seq2seq MT on multi-sentence inputs and is the single
  biggest finding for pipeline integration: a sentence-level chunking
  pass is required before either model.
- **TranslateGemma** is the only candidate that produced a complete
  three-sentence translation. It also adds interpretive context
  (`Корабль "Аргонавт"` = "the ship 'Argonaut'") and quotes proper
  nouns — over-helpful for a literal translation pass, helpful for a
  post-editing pass.
- **Term renderings differ.** "hex" → `проклятие` (NLLB; nonsense, looks
  like a token-confusion artefact), `шестигранник` (MADLAD; literal
  "hexahedron"), `соседнюю клетку` (TranslateGemma; "adjacent cell" —
  loses hex-grid). "Reaction attack" → `атаку Реакции` (NLLB/MADLAD;
  literal) vs `контратаку` (TranslateGemma; counter-attack — slight
  semantic drift).
- All three handle "Insight" as a Russian translation of the meaning
  (`Прозрение` / `Проницательность`) rather than transliteration.
  Glossary enforcement (S5U-769 / S5U-771) will need to pin these
  consistently regardless of which model wins.

## Runtime characteristics worth tracking in S5U-769

The benchmark ticket should record at least these fields per model per
run:

- **Throughput**: output tokens/sec at fixed `max_new_tokens` (this
  characterization measured 11–42 tok/s across the candidates).
- **Latency to first token** and **steady-state tok/s** separately;
  warm-up effect was 1–3 sec on bf16 / MPS.
- **Peak resident memory** (per-process), distinguished from the
  steady-state working set.
- **Sentence-recall rate** on multi-sentence inputs — NLLB and MADLAD's
  EOS-at-first-sentence behaviour is a recall failure mode benchmarks
  must measure, not just BLEU/COMET.
- **Glossary adherence** for a fixed list of game terms (Argonaut,
  Primordial, Insight, Survival, Encounter, Reaction).

## Go / no-go for the three candidates

| Candidate | Recommendation |
|-----------|----------------|
| NLLB-200 3.3B | **Conditional** — fastest of the three but needs sentence-level chunking; cheap enough to keep as a baseline |
| MADLAD-400 10B | **Conditional** — same chunking requirement, half the throughput, larger disk; only worthwhile if quality wins on the full benchmark |
| TranslateGemma 12B-it | **Recommended primary** — lowest tok/s but the only one that handled the three-sentence input intact; tuned for translation-as-instruction |

These are smoke-test verdicts on a single 70-token prompt. Final
ranking belongs to S5U-769 (corpus benchmark with COMET/BLEU + glossary
adherence) and S5U-771 (selection).

## Reproducing

The characterization script lives at `tmp/characterize_local_mt.py`
(gitignored — one-shot research code, not part of the pipeline). Each
model runs in a fresh process via:

```bash
HF_HOME="$HOME/Models/huggingface" \
  uv run --no-project --with "transformers>=4.50" --with torch \
  --with accelerate --with sentencepiece --with protobuf \
  python tmp/characterize_local_mt.py {nllb|madlad|translategemma}
```

`huggingface_hub` (for the `hf` CLI used to download the weights) is
installed via `uv tool install huggingface_hub` — a workstation tool,
not a repo-local Python dependency.

## Cross-references

- `docs/specs/local-models-cache.md` — `HF_HOME` / `OLLAMA_MODELS`
  layout this characterization assumes.
- `docs/specs/translation-providers.md` — operational surface for the
  current CLI providers; local-model providers will join this matrix.
- Linear epic `S5U-766` — parent (evaluate local open MT models for
  EN→RU).
- Linear issue `S5U-768` — wire local-model runtimes into the
  translation pipeline (consumer of these verdicts).
- Linear issue `S5U-769` — full corpus benchmark (consumer of the
  recorded fields list above).
- Linear issue `S5U-771` — final candidate selection.

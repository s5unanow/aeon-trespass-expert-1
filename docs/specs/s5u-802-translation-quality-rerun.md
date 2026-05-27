# S5U-802 Translation Quality Rerun

Status: completed local calibration run. Full generated artifacts are
gitignored under:

```text
tmp/translation-eval/s5u-776-ensemble-poc/style-v2/
```

## Command

```bash
uv run python -m scripts.translation_eval.improved_rerun 1 2
```

## Artifact Inventory

- `final/page-{1,2}-ru-final.txt` — post-repair final translations.
- `qa/page-{1,2}-qa-{v1,editor,final}.json` — deterministic QA/style findings.
- `critic/page-{1,2}-critic.json` — Codex style critic JSON.
- `repair/page-{1,2}-repair-report.json` — targeted repair report.
- `report.md` — timings, token usage, QA findings, and artifact index.
- `comparison.md` — source, old final, improved final, and human comments.

The existing `tmp/translation-eval/s5u-776-ensemble-poc/review-page-1.md`
was not overwritten.

## Results

| Page | QA v1 | QA editor | Critic findings | Repaired paragraphs | Final QA |
| --: | --: | --: | --: | -- | --: |
| 1 | 0 | 0 | 14 | 11 repaired, 1 skipped | 1 |
| 2 | 0 | 0 | 4 | 4 repaired, 0 skipped | 0 |

Page 1 final QA has one residual style finding:

```text
style_red_flag — Generic speech verb: in public prophetic address prefer
'взывает к ним' or another scene-specific verb instead of flat 'обращается к ним'.
```

## Human Comment Comparison

The rerun produced all requested artifacts, but it did not beat the
human-reviewed old final overall.

For page 1 human-commented paragraphs:

- Improved toward the human target: 1 paragraph (`P8`).
- Already matched the human target before this rerun: 3 paragraphs (`P4`, `P11`, `P24`).
- No change requested: 1 paragraph (`P9`).
- Changed but needs human spot-check: 6 paragraphs (`P3`, `P5`, `P7`, `P12`, `P13`, `P15`).
- Regressed away from the human target: 11 paragraphs (`P2`, `P6`, `P10`, `P14`, `P16`, `P17`, `P18`, `P20`, `P21`, `P22`, `P23`).

Conclusion: use `style-v2/` as calibration evidence, not as a promoted
translation baseline. The next tuning pass should focus on making critic
findings preserve accepted human rewrites instead of replacing them with
new plausible-but-weaker prose.

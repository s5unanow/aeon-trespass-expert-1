# `.claude/rules/` drift audit

**Last reviewed:** 2026-04-29 (S5U-653; verified S5U-628 follow-up gaps already closed by S5U-694 + S5U-724/727)
**Next review due:** 2026-07-18 (quarterly; manual — cadence unchanged)

This file tracks whether each `.claude/rules/*.md` still matches the codebase.
The rule files are loaded into worker-agent context on path match, so drift
between rule text and real code makes reviewers file false-positive bugs (see
the S5U-602 retrospective below). This audit is the mitigation — not a CI check.

## Audit cadence

Every quarter (or sooner if a review agent flags a rule violation that turns out
to be a false positive), re-run the audit:

1. For each rule bullet, grep the referenced tool / path / convention in the
   current tree. Note divergences.
2. For each divergence: either tighten the rule to match reality, or file a
   follow-up issue to bring the code in line.
3. Update the "Last reviewed" date at the top of this file and record the run
   under "Audit history".

No automated checker exists; out of scope for S5U-617. If drift recurs faster
than quarterly review catches it, file a follow-up to build one.

## Current verdicts (2026-04-24)

| Rule file             | Verdict                       | Action                                                      |
|-----------------------|-------------------------------|-------------------------------------------------------------|
| `pipeline.md`         | **Accurate** (post-S5U-662)   | No change (stage-cache-invalidation bullet verified current) |
| `schemas.md`          | **Accurate**                  | No change                                                   |
| `web.md`              | **Accurate**                  | No change                                                   |
| `extraction.md`       | **Accurate** (post-S5U-617)   | No change                                                   |
| `hooks.md`            | **Expanded (S5U-724)**        | Added "Hook-bypass disclosure" section with full token enumeration moved out of CLAUDE.md NEVER bullet |
| `visual-verify.md`    | **Expanded (S5U-724)**        | Added "Visual regression CI gate" section absorbing the 7 bullets moved out of CLAUDE.md lines 71–81 |
| `guards.md`           | **Accurate** (post-S5U-661)   | No change                                                   |
| `merge-discipline.md` | **New (S5U-724)**             | Added; holds admin-merge-disclosure full vector list, two-pass reviewer-probe semantics, stale-context carve-out history, and coordinator-ack mechanics rationale |

### `pipeline.md` — stale bullets

- **"Use `structlog` for all logging — no `print()` or stdlib `logging`"** —
  stale. `grep -r structlog apps/pipeline/src packages scripts` returned zero
  matches on 2026-04-18. The pipeline uses `logging.getLogger(__name__)`
  across 18+ modules: `cli/commands/run.py`, `services/llm/*`, `eval/*`,
  `stages/extract_native/evidence_vectors.py`, `stages/extract_layout/*`,
  `stages/qa/auto_fix.py`, `runner/*`, etc. Resolution: rule softened to
  "prefer `structlog` for new services needing structured context; stdlib
  `logging` is the current default and is acceptable for existing code." This
  keeps the door open for adoption without branding the existing codebase as
  broken. If the project decides to actually adopt `structlog`, file a
  migration issue and tighten the rule back.
- **"Use `orjson` with atomic writes (temp file + rename) for JSON IO"** —
  half stale. `grep -r orjson apps/pipeline/src` returns zero matches;
  stdlib `json` is used across 10+ modules. Atomic writes, however, **are**
  real: `apps/pipeline/src/atr_pipeline/store/atomic_write.py` provides
  `atomic_write_bytes` / `atomic_write_text` using `tempfile.mkstemp` +
  `os.replace`. Resolution: split the bullet — retain the atomic-write rule
  (with the helper name), drop the `orjson` mandate and note stdlib `json`
  is current practice.

### `extraction.md` — dead globs

The frontmatter globs point at paths that no longer exist (and likely never
did, post-rename to `atr_pipeline`):

```
globs: apps/pipeline/src/pipeline/extraction/**,apps/pipeline/tests/**/test_extract*
```

Real extraction code lives under
`apps/pipeline/src/atr_pipeline/stages/extract_native/**` and
`apps/pipeline/src/atr_pipeline/stages/extract_layout/**`. The test glob
`test_extract*` matches zero files; actual tests are named
`test_pymupdf_extractor.py`, `test_evidence_extractor.py`,
`test_gemini_cli_extract.py`. Resolution: globs updated to the real paths.
The rule body (follow the playbook, verify blockedBy, golden refresh) is
still correct and unchanged.

### `schemas.md` — accurate

Codegen direction (Pydantic → JSON Schema → TS) is enforced by
`make codegen` + `make check-codegen` + `scripts/check_codegen_fresh.sh`.
`packages/schemas/python/`, `packages/schemas/jsonschema/`, and
`packages/schemas/ts/` match the described layout.

### `web.md` — accurate

`apps/web/package.json` uses React 19, Vite 6, React Router 7.
`apps/web/.oxlintrc.json` enforces `import/no-cycle: error` and
`eslint/max-lines: {max: 400}`.

### `hooks.md` — accurate

`.claude/hooks/pre-commit-check.sh` uses `uv run` for all Python tools
(`uv run ruff`, `uv run mypy`, `uv run lint-imports`, `uv run pytest`) and
`pnpm` wrappers for web tools (`cd apps/web && pnpm lint`,
`cd apps/web && pnpm typecheck`). The three-input discipline and
red-before anchor (S5U-615) are documented inline and probed by
`.claude/prompts/review.md`.

### `visual-verify.md` — accurate

References to `localhost:3001`, `apps/web/tests/e2e/__snapshots__/`,
`test:visual:update`, and the S5U-599/608 baseline-update flow are all
current. Paths `scripts/export_to_web.py`, `scripts/_export_blocks.py`, and
`apps/pipeline/src/atr_pipeline/stages/render/` all exist.

## S5U-602 retrospective

S5U-602 was filed as "ingest_user_feedback.py violates the structlog rule"
even though an immediate grep showed the rest of the pipeline uses stdlib
`logging` everywhere. The reviewer trusted the rule over the code. The
right answer was to fix the rule, not the script. This audit is the fix:
the rule is now softened so the next reviewer's grep and the rule's text
agree.

## Audit history

- 2026-04-18 (S5U-617): initial audit; reconciled `pipeline.md` (structlog,
  orjson bullets) and `extraction.md` (dead globs). All other rule files
  verified accurate.
- 2026-04-20 (S5U-661): added `guards.md` codifying CI-guard discipline
  (Rule G1 fail-closed defaults; Rule G2 content-derived sets over
  hardcoded name lists). The rule is wired as a sub-bullet of
  `.claude/prompts/review.md` check #16 (safety gate bypass), so any diff
  touching `scripts/check_*.py`, `scripts/check_*.sh`, or workflow `run:`
  guard steps triggers an explicit G1/G2 audit. This is not a retroactive
  fix of existing guards — instance fixes S5U-637 (G2, visual-gate-scope)
  and S5U-642 (G1, threshold-guard shallow checkout) shipped separately
  and stand as precedents cited in the rule retrospectives. Did not
  re-verify other rule files this cycle; the S5U-617 accuracy findings
  for `pipeline.md` / `extraction.md` / `schemas.md` / `web.md` /
  `hooks.md` / `visual-verify.md` are carried forward. Next full audit
  due 2026-07-18 on the original quarterly cadence.
- 2026-04-20 (S5U-662): added the **Stage-output cache invalidation**
  bullet to `pipeline.md` codifying the rule that a new artifact write
  or persisted record in a stage's `run()` requires (1) bumping the
  stage class's `version` field in the same PR and (2) a regression
  test exercising the executor's cache-hit path. The rule is backed by
  a new reviewer probe — `.claude/prompts/review.md` check #23 — that
  fires a WARNING when a stage.py diff adds `put_json` / `put_binary`
  / `atomic_write_*` without a visible `version = "x.y"` change.
  Motivated by the S5U-597 → S5U-640 retrospective, where the
  `qa_metrics.json` artifact added in S5U-597 was silently omitted on
  cached runs until the version was bumped in S5U-640. Not a retroactive
  fix — S5U-640 shipped separately; this PR codifies the meta-rule.
  Did not re-verify other rule files this cycle; carry-forward applies.
  Next full audit due 2026-07-18.
- 2026-04-24 (S5U-724): extracted retrospective prose from CLAUDE.md
  into referenced rule files to shrink the hot-path doc from 243 to
  under 160 lines per the external-review sweet-spot finding. Three
  extractions:
  (1) Visual regression gate subsection (CLAUDE.md lines 71–81 with
  S5U-599/608/611/639/709 retrospectives) → `.claude/rules/visual-verify.md`
  § "Visual regression CI gate (S5U-599)". CLAUDE.md keeps a 5-bullet
  short form + pointer. (2) NEVER §hook-bypass bullet (S5U-629/672
  token-enumeration prose) → `.claude/rules/hooks.md` § "Hook-bypass
  disclosure (S5U-629, extended S5U-672)". (3) NEVER §admin-merge bullet
  (S5U-671/675/664 two-pass-probe and carve-out prose) + §6
  coordinator-ack rationale (S5U-670/693 file-marker-retire history)
  → new `.claude/rules/merge-discipline.md` with two sections
  ("Admin-merge disclosure" and "Coordinator-ack mechanics"). Updated
  reviewer-probe citations: `.claude/prompts/review.md:182` replaced
  `CLAUDE.md:206` with a stable section-anchor reference to
  `.claude/rules/hooks.md § "Hook-bypass token enumeration"`. Updated
  three skill files (`next`, `build-loop`, `ship`) that cited
  `CLAUDE.md:154` — replaced the line number with the stable section
  anchor "Bypass clauses (must-refuse, S5U-614)". Verified that
  `scripts/check_instruction_drift.py`'s canonical `safety-gate scope
  (...)` parenthetical regex still matches the preserved CLAUDE.md
  paragraph. Not a retroactive rule addition — the underlying rules
  are unchanged; only the prose location moved. Next full audit due
  2026-07-18.
- 2026-04-29 (S5U-653): verification audit for the S5U-628 follow-up
  drift filed 2026-04-19. Both gaps reported in S5U-653 are already
  closed by intervening work and `check_instruction_drift.py` now
  mechanically enforces the parities the issue called for:
  (a) Safety-gate scope enumeration in CLAUDE.md (`step 6` /
  "Safety-gate scope escalation (MUST)") includes
  `.claude/skills/**/SKILL.md` edits in the canonical parenthetical.
  Rule C (`scripts/_instruction_drift_rule_c.py`) extracts the
  parenthetical and enforces every cited form in
  `.claude/skills/**/SKILL.md` and `.claude/prompts/**.md` matches
  byte-for-byte (or defers with `per CLAUDE.md`). Gap closed by
  S5U-724 (canonical paragraph preserved) + S5U-727 (Rule C lifted
  into a module).
  (b) Path B check-count reference in CLAUDE.md `step 6` table reads
  `walk review.md checks 1–25`; `.claude/skills/ship/SKILL.md:46`
  reads `walk all 25 checks in `.claude/prompts/review.md``. The
  authoritative numbered list in `.claude/prompts/review.md` runs
  1–25. Rule A (claim drift) + Rule E (CI gate count drift) both
  return clean on `main`:
  `check_instruction_drift: OK (authoritative review checks: 1-25;
  scanned 51 .md files)`. Gap closed by S5U-694 (drift detector
  parity enforcement) + downstream maintenance. Audit limited to
  drift verification; no rule-file edits. The only operational
  occurrences of `1-2[1-4]` outside `_instruction_drift_rule_a.py`
  examples and `test_check_instruction_drift*.py` fixtures are zero
  (full repo grep). Next full audit still due 2026-07-18.

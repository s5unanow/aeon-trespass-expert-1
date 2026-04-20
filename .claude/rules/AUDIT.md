# `.claude/rules/` drift audit

**Last reviewed:** 2026-04-20 (S5U-661; `guards.md` added)
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

## Current verdicts (2026-04-20)

| Rule file         | Verdict                    | Action                                                      |
|-------------------|----------------------------|-------------------------------------------------------------|
| `pipeline.md`     | **Accurate** (post-S5U-617)| No change (softened in S5U-617; verified still current)     |
| `schemas.md`      | **Accurate**               | No change                                                   |
| `web.md`          | **Accurate**               | No change                                                   |
| `extraction.md`   | **Accurate** (post-S5U-617)| No change (globs fixed in S5U-617; verified still current)  |
| `hooks.md`        | **Accurate**               | No change                                                   |
| `visual-verify.md`| **Accurate**               | No change                                                   |
| `guards.md`       | **New (S5U-661)**          | Added; codifies G1 fail-closed + G2 content-derived sets    |

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

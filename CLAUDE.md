# CLAUDE.md

**Purpose**: Claude Code entrypoint for `aeon-trespass-expert`. Canonical guidance lives in `AGENTS.md` and `.ai-run/guides/`.

<!-- ai-run-init:guide-imports start -->
@AGENTS.md
<!-- ai-run-init:guide-imports end -->

---

The sections below are **machine-scanned anchors**: fail-closed repo guards parse them from this file specifically (`scripts/check_make_doc_parity.py` reads the `make lint` summary line; `scripts/check_instruction_drift.py` Rules C/E/F/G read the safety-gate-scope parenthetical and the CI gate enumeration; `.claude/skills/**/SKILL.md` cite "per CLAUDE.md"). They stay here verbatim and change only in lockstep with the `Makefile`, CI workflows, and `.claude/prompts/review.md`. Human-oriented guidance for the same topics: `AGENTS.md`, `.ai-run/guides/quality-gates.md`, `.ai-run/guides/standards/development-workflow.md`.

## Commands

```bash
make bootstrap                # Install all deps (uv sync + pnpm install)
make lint                     # ruff check + ruff format --check + mypy + import-linter + file-length + fixture-manifest + instruction-drift + make/doc parity + codegen freshness + pnpm lint
make check                    # Aggregate: lint + typecheck + test (the canonical local "definition of done")
make typecheck test codegen   # mypy + tsc / all tests / regenerate JSON Schema + TS types from Pydantic
make check-codegen            # Verify generated schemas match Pydantic sources
make verify-branch-protection # Audit live main branch protection against workflow policy
make export format clean      # Export to web public / auto-fix formatting / remove caches
```

## Quality gates

Two tiers of checks run at different stages. Both must pass.

### Local (pre-commit hook, 9 checks: 1 secret guard + 8 quality gates) — runs on `git commit` via `.claude/hooks/pre-commit-check.sh`, <60 s target

0. `secret guard` — blocks staged secrets (filenames: `.env`, `*.key`, `*.pem`, `credentials.json`; content: `sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers)
1. `ruff check` — lint (includes McCabe complexity C901, max 12)
2. `ruff format --check` — format violations
3. `mypy --strict` — type errors
4. `lint-imports` — import layer contracts (no cyclic dependencies)
5. `check_file_length.py` — max 400 lines per source and test file (pre-existing violators grandfathered in `KNOWN_VIOLATORS` and must not grow)
6. `oxlint` — frontend lint (`import/no-cycle`, `max-lines: 400`)
7. `tsc --noEmit` — frontend type check
8. `pytest -x -q --timeout=60 -m "not slow"` — fast test subset only

### CI (GitHub Actions, 9 + 9 extra) — runs on every push to `main` and every PR; includes all 9 local gates plus:

9. `check_codegen_fresh.sh` — generated JSON Schema + TS types match Pydantic sources (also `make check-codegen`).
10. `validate_fixture_manifest.py` — fixture integrity (also `make validate-fixtures`).
11. `check_extraction_scope.py` — CI-only (needs base-branch comparison); reports when a PR touches extraction scope.
12. `check_golden_refresh.py` — CI-only (needs base-branch comparison); gates golden refreshes when extraction scope is detected.
13. `visual-regression / visual` — Playwright `toHaveScreenshot` at `maxDiffPixelRatio: 0.005`. Full stack in `.claude/rules/visual-verify.md` § "Visual regression CI gate".
14. `visual-gate-scope / scan` — content-derived scan of workflow YAML and `apps/web/package.json` for flags that bypass the visual-regression gate. See `.claude/rules/guards.md` Rule G2.
15. `coverage-table-scan / scan` — on `pull_request`, enforces the Coverage table on ≥3-bullet Linear issues. Requires `LINEAR_API_KEY`.
16. `check_instruction_drift.py` — scans `*.md` for stale check-count claims, retired-term leaks, and drifted safety-gate-scope enumerations. Runs inside `python / test`. Now also enforces CI gate count parity between the header, the enumerated list, and `all K gates` claims (Rule E, S5U-694).
17. `check_make_doc_parity.py` — fails CI when `make lint` in the `Makefile` drifts from the one-line summaries in CLAUDE.md and load-bearing templates (e.g. `docs/EXTRACTION_TICKET_TEMPLATE.md`). Fail-closed on missing `Makefile`/`CLAUDE.md`/template per `.claude/rules/guards.md` Rule G1. Runs inside `python / test` (S5U-690, PR #307).

CI also runs `pytest --tb=short` (full suite — includes slow tests, no timeout), unlike the pre-commit fast subset.

### What "passing" means

- **Local green** = safe to commit and push, but not sufficient for merge.
- **CI green** = all 18 gates pass — required for merge. "Definition of Done" means CI green.

## Independent fresh-eyes review (MANDATORY before PR)

Review-path selection is **determined by whether the `Agent` tool is in your direct tool list**, not by preference.

| Is `Agent` in my direct tool list? | Path | What to do                                                                                                                                                                                                                |
|------------------------------------|------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Yes (top-level coordinator)        | A    | Spawn an independent review agent with `.claude/prompts/review.md`. Brief as a stranger (Linear ID, branch, cwd only — no rationale, commit messages, draft PR body). Reviewer writes `tmp/review-s5u-<N>.md`. BLOCK → fix and re-review (delete stale artifact first). |
| No (sub-agent under `/build-loop`, `/coordinator`, `/next`, `/ship`) | B    | Inline self-review: close drafts, re-fetch the Linear issue, read the diff unanchored, walk review.md checks 1–25, produce `tmp/review-s5u-<N>.md` with the same structured verdict. Disclose the fallback in both the artifact and PR body. |

Both paths must produce the same structured verdict (`Verdict:`, `Critical:`, `Warning:`, `Suggestion:`, `Probes run:` with ≥3 bullets, `Bug IDs filed:`). The pre-PR hook (`pre-pr-check.sh`) enforces the artifact contract on local `gh pr create` (the GitHub web UI / REST API bypass it). Path B disclosure (paste verbatim into the review artifact and PR body): `"Reviewed under Path B (Agent tool unavailable in this sub-agent context, per CLAUDE.md step 6 / S5U-628). Authoritative post-ship review is the top-level coordinator's responsibility."` Claiming Path B at the top level to avoid the spawn is a safety-gate violation.

**Safety-gate scope escalation (MUST):** any PR touching safety-gate scope (hooks, pre-commit checks, review gates, CI checks, merge guards, branch-protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits) MUST be shipped via `/coordinator`, not via `/ship` / `/next` / `/build-loop` run as a lone worker. The coordinator spawns a separate post-ship fresh-eyes reviewer in a new sub-agent context — that reviewer is the authoritative gate. **Mechanical enforcement:** `pre-pr-check.sh` refuses `gh pr create` on safety-gate-scoped branches unless the GitHub API returns a `coordinator-ack` commit status (state=success, context=coordinator-ack) on the branch HEAD from a signer in `.claude/coordinator-signers.txt` (S5U-670). **Post-merge audit layer:** `.github/workflows/post-merge-coordinator-ack.yml` re-checks every `push` to `main` for safety-gate-scoped diffs and fails if no valid coordinator-ack is found (S5U-693). The workflow is not a required-check context — it is a durable audit signal the reviewer's check #16 cross-references. Full rationale (why file-marker was retired, why the coordinator-signers allowlist, how the post-merge audit closes the web-UI / REST bypass) in `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics".

**Bypass clauses (must-refuse, S5U-614):** (1) safety-gate changes MUST NOT ship via `/ship` / `/next` / `/build-loop` without a coordinator-style post-ship review; (2) Path B MUST NOT be invoked when `Agent` is actually available ("Agent was slow" is not a valid reason); (3) Path B MUST NOT substitute for Codex review on `cross-system-review`-labeled issues; (4) the fallback MUST NOT be satisfied by an out-of-harness channel (custom API script, separate Claude terminal / web chat, local LLM) — those skip the harness artifact contract.

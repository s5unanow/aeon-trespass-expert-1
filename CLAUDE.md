# CLAUDE.md — Aeon Trespass Expert

## What this is

IR-first document compiler + static web reader for Aeon Trespass rulebook translation (EN->RU).
Monorepo with two products:

- **apps/pipeline** — Python 3.12 content compiler (PDF -> IR -> translate -> QA -> site bundle)
- **apps/web** — React 19 / Vite static reader that renders the bundle

## Repo layout

```
apps/pipeline/       Python pipeline (uv, pydantic, typer, structlog)
apps/web/            React 19 / Vite / React Router 7 (pnpm, Storybook)
packages/schemas/    Shared schemas: python/ (Pydantic) -> jsonschema/ -> ts/ (generated TS types)
configs/             TOML configs: documents, base, ci, glossary, symbols
scripts/             Codegen, fixture bootstrap, export utilities
artifacts/           Pipeline output (gitignored run data)
docs/                Architecture docs (read on demand, not memorized)
```

## Commands

```bash
make bootstrap        # Install all deps (uv sync + pnpm install)
make lint             # ruff check + mypy + import-linter + file-length + codegen freshness + pnpm lint
make typecheck        # mypy + tsc
make test             # All tests (pytest + pnpm test)
make codegen          # Regenerate JSON Schema + TS types from Pydantic models
make check-codegen    # Verify generated schemas match Pydantic sources
make export           # Export pipeline artifacts to web public (re-generates documents/)
make format           # Auto-fix formatting (ruff format + ruff check --fix + pnpm format)
make clean            # Remove caches and build artifacts
```

## Quality gates

Two tiers of checks run at different stages. Both must pass.

### Local (pre-commit hook, 9 checks: 1 secret guard + 8 quality gates)

Runs automatically on every `git commit` via `.claude/hooks/pre-commit-check.sh`. Fast — targets < 60 s.

0. `secret guard` — blocks staged secrets (filenames: `.env`, `*.key`, `*.pem`, `credentials.json`; content: `sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers)
1. `ruff check` — lint (includes McCabe complexity C901, max 12)
2. `ruff format --check` — format violations
3. `mypy --strict` — type errors
4. `lint-imports` — import layer contracts (no cyclic dependencies)
5. `check_file_length.py` — max 400 lines per source file
6. `oxlint` — frontend lint (`import/no-cycle`, `max-lines: 400`)
7. `tsc --noEmit` — frontend type check
8. `pytest -x -q --timeout=60 -m "not slow"` — fast test subset only

### CI (GitHub Actions, 9 + 7 extra)

Runs on every push to `main` and on every PR. Includes all 9 local gates plus:

9. `check_codegen_fresh.sh` — verifies generated JSON Schema + TS types match Pydantic sources. *Also available locally via `make check-codegen` and included in `make lint`.*
10. `validate_fixture_manifest.py` — fixture integrity checks. *CI-only because it can be slow with large fixture sets.*
11. `check_extraction_scope.py` — detects extraction-related changes in PRs. *CI-only because it compares against the PR base branch.*
12. `check_golden_refresh.py` — validates golden file updates when extraction scope is detected. *CI-only because it requires base-branch comparison and only triggers conditionally.*
13. `visual-regression / visual` — Playwright `toHaveScreenshot` assertions against committed baselines under `apps/web/tests/e2e/__snapshots__/`, enforced at `maxDiffPixelRatio: 0.005`. A missing or mismatched baseline fails the job and blocks merge. See "Visual regression gate (S5U-599)" below for the baseline-update flow. *CI-only because baseline rendering must happen on the pinned Linux runner; developers regenerate locally only when changing a curated component intentionally.*
14. `visual-gate-scope / scan` — scans every YAML under `.github/workflows/` and `.github/actions/`, plus every `apps/web/package.json` script, for Playwright flags that would bypass the visual-regression gate (`-u`, `--update-snapshots`, `--ignore-snapshots`) and for workflow references to local-only update scripts (`test:visual:update`). Added in S5U-608 to close the bypass vectors found in the second-pass review of S5U-599. See `scripts/check_visual_gate_scope.py`.
15. `coverage-table-scan / scan` — on every `pull_request: [opened, synchronize, edited, reopened]`, re-reads the live PR body, counts Linear Fix+Success-criteria bullets (every list marker at every indent level per S5U-622), and fails the job if the body lacks a `## Coverage` section on a ≥3-bullet issue, if the table has fewer rows than the bullet count, or if a `deferred to S5U-YYY` row cites a non-existent or Canceled Linear issue. Added in S5U-620 to close the `gh pr edit --body` bypass that `pre-pr-check.sh` cannot see. Requires the `LINEAR_API_KEY` repo secret — fails CLOSED if absent. See `scripts/check_coverage_table.py` and `tmp/plan-s5u-620.md`.

CI also runs `pytest --tb=short` (full suite — includes slow tests, no timeout), unlike the pre-commit fast subset.

### Visual regression gate (S5U-599)

- **Baselines** live at `apps/web/tests/e2e/__snapshots__/*.png` and are committed to git. They are the ground truth; every PR is diffed against them.
- **Threshold**: `maxDiffPixelRatio: 0.005` (0.5% of pixels may differ). Configured centrally in `apps/web/playwright.config.ts`. Do not loosen without a linked issue explaining why. Avoid per-test overrides; if you need one, justify in the PR.
- **Intentional baseline update** (legitimate UI change): run `pnpm --filter @atr/web run test:visual:update` locally, inspect the regenerated PNGs under `apps/web/tests/e2e/__snapshots__/`, and commit the diff in a dedicated commit (`S5U-XXX: refresh visual baselines — <why>`). The reviewer must confirm the visual delta is intentional.
- **CI never regenerates baselines**: enforcement is two-layer. (1) A job-local guard (`scripts/check_test_e2e_flags.sh`) in `.github/workflows/visual-regression.yml` fails the job if `apps/web/package.json`'s `test:e2e` script contains `-u`, `--update-snapshots`, or `--ignore-snapshots`. (2) The separate `visual-gate-scope / scan` job (`scripts/check_visual_gate_scope.py`) scans every workflow/action YAML and every package.json script for those flags, and blocks any workflow `run:` line that invokes `test:visual:update`. Do not add those flags to any CI command under any circumstance. See S5U-608 for the full threat model and the adversarial test matrix in `tmp/plan-s5u-608.md` and `apps/pipeline/tests/unit/test_check_visual_gate_scope.py`.
- **New curated pages**: add a `toHaveScreenshot('page-id.png')` assertion in `apps/web/tests/e2e/*.spec.ts`, generate the baseline locally via `test:visual:update`, and commit both the spec change and the PNG.
- **Platform note**: baselines are captured on the Linux CI runner. On macOS/Windows dev machines, anti-aliasing and font hinting typically produce 2–4% pixel drift even without code changes, which will exceed the 0.005 threshold. This is expected. The authoritative run is CI. When you refresh baselines locally to push an intentional UI change, CI will re-verify them on Linux; if they fail on CI, pull the refreshed PNGs from the CI test-results artifact and commit those instead.

### What "passing" means

- **Local green** = safe to commit and push, but not sufficient for merge.
- **CI green** = all 16 gates pass — required for merge. "Definition of Done" means CI green.

## Development workflow (MANDATORY)

All work is tracked in **Linear** (project **ATE1**, team **S5U**). Every change follows this workflow — no exceptions.

### 1. Pick up an issue
- If the user specifies an issue, use that one
- **If no issue is specified, auto-pick**: query Linear for the highest-priority unassigned issue in the earliest milestone: `mcp__linear__list_issues(project="ATE1", state="Backlog")` — pick the first Urgent, then High, then Normal
- Update issue status to **In Progress**: `mcp__linear__save_issue(id="S5U-XXX", state="In Progress")`

### 2. Create a branch
- Branch from `main`: `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description`
- Branch naming is **enforced by hook** — must match `s5unanow/s5u-<number>-<description>`
- Direct commits to `main` are **blocked by hook**
- Dirty working tree on main is **blocked by hook** — stash or discard before branching

### 3. Plan before coding (cross-subsystem changes)
- **If the issue touches more than one subsystem** (pipeline + web, export + render, config + stage, schemas + pipeline, etc.), **run the planning prompt first**: read `.claude/prompts/plan.md` and use it as the Agent prompt
- The plan identifies cross-subsystem invariants, blast radius, and test strategy *before* any code is written
- Save the plan to `tmp/plan-s5u-<NUMBER>.md`
- Single-subsystem changes skip this step — **except** safety-gate changes (hooks, review gates, CI checks, merge guards), which always require the plan prompt to document adversarial scenarios

### 4. Work on the branch
- Commit early and often with prefix `S5U-XXX: description`
- The 9 local gates run automatically before each commit via hook

### 5. Definition of done (all must be true before PR)
- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] **New/changed tests verified red-before** — for each new `def test_` (pytest) or `it(`/`test(` (vitest) the commit message or PR body contains a `Red-before confirmation:` line citing a pre-fix SHA, a failure-output excerpt, or an explicit "N/A — no production code change" carve-out. See `.claude/rules/hooks.md` § "Three-input test discipline" for the authoritative form. Motivated by S5U-615 after S5U-606 / S5U-604 false-greens.
- [ ] **Coverage table (multi-bullet issues only)** — if the Linear issue has **≥3 explicit bullets across its "Fix" + "Success criteria" sections** (counting every list marker at any indent level — nested sub-bullets count), the PR body must include a Coverage table listing **one row per bullet, verbatim** (do not merge rows, do not collapse nested sub-bullets under the parent) mapping each bullet to the commit/file that addresses it, or an explicit `"deferred to S5U-XXX"` with a linked Linear follow-up (the follow-up must exist and not be Canceled). Single-bullet or prose-style issues are exempt — reviewer judgment applies. See `.claude/prompts/linear-conventions.md` § "Coverage table format (multi-bullet issues)" for the worked example. Motivated by S5U-616 after S5U-594 / S5U-595 / S5U-605 dropped-bullet regressions; nested-bullet semantics clarified in S5U-622.
- [ ] No violations of the **NEVER** list (see below)
- [ ] Local gates pass: `make lint && make typecheck && make test`
- [ ] CI green after push (all 16 gates — local green alone is not sufficient)
- [ ] If adding/modifying a safety gate: adversarial scenarios documented in `tmp/plan-s5u-<NUMBER>.md` and each one either holds or has been fixed

### 6. Independent fresh-eyes sub-agent review (MANDATORY before PR)
- **You MUST spawn an independent review agent before creating a PR.** This is not optional.
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- **Brief the reviewer as a stranger.** Pass only: Linear issue ID, branch name, working directory, and the reminder that the worker is not them. Do **NOT** paste your rationale, deviations list, commit messages, or draft PR body into the sub-agent brief — these anchor the reviewer on your framing and defeat the point of independent review. The reviewer fetches the Linear issue and diff itself and forms its own read.
- The reviewer must emit a **structured verdict block** (the `## Verdict` section contract in `.claude/prompts/review.md`) with `Verdict:`, `Critical:`, `Warning:`, `Suggestion:`, `Probes run:`, and `Bug IDs filed:` fields. The pre-PR hook (`pre-pr-check.sh`) enforces this contract: missing fields, fewer than 3 probe bullets, a `BLOCK` verdict, or an artifact older than the branch's HEAD commit all cause `gh pr create` to fail.
- If the review agent says **BLOCK**, fix the issues and re-run the review (delete the stale artifact first). Do **not** amend the old artifact.
- If only warnings/nits, use judgement — fix warnings, nits are optional. Include unresolved warnings in the PR body.
- Known carveout: the hook only intercepts local `gh pr create`. Opening a PR via the GitHub web UI or REST API bypasses the gate — do not do this to skip review.

### 7. Create PR
- Push branch: `git push -u origin HEAD`
- Create PR via `gh pr create` with summary and test plan
- Link the Linear issue in PR body

### 8. Wait for CI
- Check CI status: `gh pr checks <pr-number> --watch`
- If CI fails, fix and push — do not merge with red CI
- **Branch protection enforces this**: GitHub blocks merge if any required check (`python / test`, `web / test`, `visual-regression / visual`) is red. The visual-regression check is a hard gate — if it fails, either fix the regression or regenerate baselines per the "Visual regression gate (S5U-599)" section above

### 9. Merge and sync
- Merge via: `gh pr merge <pr-number> --squash --delete-branch`
- Sync local: `git checkout main && git pull`
- **Check main CI before merge**: before running `gh pr merge`, verify the latest CI run on `main` is green **and its `headSha` matches current main HEAD** (`gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'`). If the SHA doesn't match (stale run from dispatch latency), retry up to 3× with 10 s delay. If main is red, fix it first. If in-progress, wait. Do not batch-merge — cascading failures propagate undetected when merges skip CI verification.
- Update Linear issue to **Done**: `mcp__linear__save_issue(id="S5U-XXX", state="Done")`

### Rollback process
If a merged PR breaks something:
1. Identify the merge commit: `git log --oneline main`
2. Revert it: `git revert <commit-sha>` (creates a new commit, does NOT rewrite history)
3. Push the revert, open a new PR for the fix
4. Reopen the Linear issue and set back to **In Progress**

### Emergency bypass (admin only)
Branch protection on `main` requires all CI checks to pass before merge. If a genuine emergency requires bypassing (e.g., CI infrastructure is down, not a code failure):
1. A repo admin can merge via the GitHub UI using **"Merge without waiting for requirements"**
2. Document the bypass reason in the PR description
3. Open a follow-up issue to address the underlying failure
4. **Never bypass for code test failures** — fix the tests first

## Conventions

- **Commit prefixes**: `S5U-XXX:` referencing the Linear issue
- **Config format**: TOML for all pipeline/document configuration
- Path-specific conventions (Python, TypeScript, extraction, schemas) are in `.claude/rules/` — loaded automatically when touching matching paths
- **Linear issue conventions**: read `.claude/prompts/linear-conventions.md` before creating or updating Linear issues
- **Scripts before skills**: before invoking a slash-command skill for batch or multi-step work, check `scripts/` for a purpose-built tool (e.g., `scripts/run-issues.sh` for batch issue runs — use this instead of `/build-loop`)

## NEVER

- Never use `git reset --hard` or `git push --force` on main
- Never commit .env, credentials, API keys, or secret files
- Never write manual TypeScript types (generate from Pydantic via codegen)
- Never add bare `except Exception` without structured logging
- Never skip the sub-agent review before creating a PR
- Never commit directly to main (use feature branches)
- Never merge with failing CI

## Compact Instructions

When compressing conversation context, always preserve:

- The **Linear issue ID** (`S5U-XXX`) currently being worked on
- The **current branch name** and its relationship to the issue
- Which **quality gates** have passed or failed in this session
- **Architectural decisions** made during the session and their rationale
- The **definition-of-done checklist** state (which items are checked/unchecked)
- Any **blocking issues** or unresolved problems encountered

## Session handoff

Before ending a long session (context limit approaching, user break, or switching issues), write `HANDOFF.md` in the repo root with:

- What was tried and what worked
- What failed and why
- Current state (which gates pass, what's left on the checklist)
- What should happen next

The next session starts by reading this file. `HANDOFF.md` is ephemeral and gitignored — it is not committed.

## Context management

- Use `/compact` between task phases within the same issue
- Use `/clear` when switching to a different issue
- Use `/context` to inspect token consumption in long sessions
- For task switches, prefer `/clear`; for a new phase of same task, use `/compact`

## Current state

All work is tracked in Linear (project ATE1). Check `mcp__linear__list_issues(project="ATE1")` for current status.

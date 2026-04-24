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
make bootstrap                # Install all deps (uv sync + pnpm install)
make lint                     # ruff check + ruff format --check + mypy + import-linter + file-length + fixture-manifest + make/doc parity + codegen freshness + pnpm lint
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
11. `check_extraction_scope.py` / 12. `check_golden_refresh.py` — CI-only (need base-branch comparison); gate golden refreshes when extraction scope is detected.
13. `visual-regression / visual` — Playwright `toHaveScreenshot` at `maxDiffPixelRatio: 0.005`. Full stack in `.claude/rules/visual-verify.md` § "Visual regression CI gate".
14. `visual-gate-scope / scan` — content-derived scan of workflow YAML and `apps/web/package.json` for flags that bypass the visual-regression gate. See `.claude/rules/guards.md` Rule G2.
15. `coverage-table-scan / scan` — on `pull_request`, enforces the Coverage table on ≥3-bullet Linear issues. Requires `LINEAR_API_KEY`.
16. `check_instruction_drift.py` — scans `*.md` for stale check-count claims, retired-term leaks, and drifted safety-gate-scope enumerations. Runs inside `python / test`. Now also enforces CI gate count parity between the header, the enumerated list, and `all K gates` claims (Rule E, S5U-694).
17. `check_make_doc_parity.py` — fails CI when `make lint` in the `Makefile` drifts from the one-line summaries in CLAUDE.md and load-bearing templates (e.g. `docs/EXTRACTION_TICKET_TEMPLATE.md`). Fail-closed on missing `Makefile`/`CLAUDE.md`/template per `.claude/rules/guards.md` Rule G1. Runs inside `python / test` (S5U-690, PR #307).

CI also runs `pytest --tb=short` (full suite — includes slow tests, no timeout), unlike the pre-commit fast subset.

### Visual regression gate (S5U-599)

- **Baselines** live at `apps/web/tests/e2e/__snapshots__/*.png` and are the ground truth; every PR is diffed against them at `maxDiffPixelRatio: 0.005` (configured in `apps/web/playwright.config.ts`).
- **Intentional baseline update**: run `pnpm --filter @atr/web run test:visual:update` locally and commit the regenerated PNGs in a dedicated commit.
- **CI never regenerates baselines** — two-layer enforcement (`scripts/check_test_e2e_flags.sh` job-local guard + `visual-gate-scope / scan` content-derived scan). Adding a new required-check context uses the **append-only** endpoint `POST .../required_status_checks/contexts`; `PATCH` / `PUT` both REPLACE the full list.
- **Live audit**: `make verify-branch-protection` checks the live `main` protection against workflow-derived expectations after any workflow change.
- See `.claude/rules/visual-verify.md` § "Visual regression CI gate (S5U-599)" for the full enforcement-stack history, branch-protection append worked examples, and platform-drift note.

### What "passing" means

- **Local green** = safe to commit and push, but not sufficient for merge.
- **CI green** = all 18 gates pass — required for merge. "Definition of Done" means CI green.

## Development workflow (MANDATORY)

All work is tracked in **Linear** (project **ATE1**, team **S5U**). Every change follows this workflow — no exceptions.

### 1. Pick up an issue
- User-specified, or auto-pick highest-priority unassigned Backlog issue (Urgent → High → Normal): `mcp__linear__list_issues(project="ATE1", state="Backlog")`.
- Mark In Progress via `mcp__linear__save_issue`.

### 2. Create a branch
- `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description`. Branch naming, direct commits to main, and dirty-tree-on-main are all enforced by hook.

### 3. Plan before coding
- Cross-subsystem changes (pipeline + web, export + render, schemas + pipeline, etc.): read `.claude/prompts/plan.md` as the Agent prompt, save plan to `tmp/plan-s5u-<N>.md`.
- Single-subsystem changes skip this — **except** safety-gate changes (hooks, review gates, CI checks, merge guards), which always require the plan to document adversarial scenarios.

### 4. Work on the branch
- Commit with prefix `<issue-id>: description`. The 9 local gates run automatically before each commit via hook.

### 5. Definition of done (all must be true before PR)
- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] **New/changed tests verified red-before** — each new `def test_` (pytest) or `it(`/`test(` (vitest) needs a `Red-before confirmation:` line in the commit message or PR body citing a pre-fix SHA, failure excerpt, or "N/A — no production code change" carve-out. Authoritative form and SHA-resolution tripwire in `.claude/rules/hooks.md` § "Three-input test discipline".
- [ ] **Coverage table (multi-bullet issues only)** — Linear issues with ≥3 explicit bullets across "Fix" + "Success criteria" need a Coverage table in the PR body — one row per bullet verbatim, mapping each to a commit/file or a deferred-to-followup row with a live Linear reference. See `.claude/prompts/linear-conventions.md` § "Coverage table format".
- [ ] No violations of the **NEVER** list (see below)
- [ ] Local gates pass: `make lint && make typecheck && make test`
- [ ] CI green after push (all 18 gates — local green alone is not sufficient)
- [ ] If adding/modifying a safety gate: adversarial scenarios documented in `tmp/plan-s5u-<NUMBER>.md` and each one either holds or has been fixed

### 6. Independent fresh-eyes review (MANDATORY before PR)

Review-path selection is **determined by whether the `Agent` tool is available in your direct tool list**, not by preference. Sub-agents spawned by `/build-loop`, `/coordinator`, `/next`, and `/ship` do NOT have the `Agent` tool; the top-level coordinator context does (S5U-628).

**Path A — `Agent` tool available.** Spawn an independent review agent before creating a PR. Use `.claude/prompts/review.md` as the prompt. Brief the reviewer as a stranger — pass only Linear issue ID, branch name, working directory. Do NOT paste your rationale, commit messages, or draft PR body. The reviewer must emit the structured verdict block (`Verdict:`, `Critical:`, `Warning:`, `Suggestion:`, `Probes run:` with ≥3 bullets, `Bug IDs filed:`) to `tmp/review-s5u-<N>.md`; the pre-PR hook (`pre-pr-check.sh`) enforces the contract. BLOCK → fix and re-review (delete stale artifact first). Carveout: the hook only intercepts local `gh pr create`; the GitHub web UI / REST API bypass it.

**Path B — `Agent` tool NOT available (sub-agent fallback).** Perform maximum-independence inline self-review: close drafts, re-fetch the Linear issue, read the diff unanchored, walk review.md checks 1–25, produce `tmp/review-s5u-<N>.md` with the same structured verdict. Disclose the fallback in both the review artifact and PR body: `"Reviewed under Path B (Agent tool unavailable in this sub-agent context, per CLAUDE.md step 6 / S5U-628). Authoritative post-ship review is the top-level coordinator's responsibility."` The fallback is only valid when `Agent` is genuinely missing — claiming Path B at the top level to avoid the spawn is a safety-gate violation.

**Safety-gate scope escalation (MUST):** any PR touching safety-gate scope (hooks, pre-commit checks, review gates, CI checks, merge guards, branch-protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits) MUST be shipped via `/coordinator`, not via `/ship` / `/next` / `/build-loop` run as a lone worker. The coordinator spawns a separate post-ship fresh-eyes reviewer in a new sub-agent context — that reviewer is the authoritative gate. **Mechanical enforcement:** `pre-pr-check.sh` refuses `gh pr create` on safety-gate-scoped branches unless the GitHub API returns a `coordinator-ack` commit status (state=success, context=coordinator-ack) on the branch HEAD from a signer in `.claude/coordinator-signers.txt` (S5U-670). **Post-merge audit layer:** `.github/workflows/post-merge-coordinator-ack.yml` re-checks every `push` to `main` for safety-gate-scoped diffs and fails if no valid coordinator-ack is found (S5U-693). The workflow is not a required-check context — it is a durable audit signal the reviewer's check #16 cross-references. Full rationale (why file-marker was retired, why the coordinator-signers allowlist, how the post-merge audit closes the web-UI / REST bypass) in `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics".

**Bypass clauses (must-refuse, S5U-614):** (1) safety-gate changes MUST NOT ship via `/ship` / `/next` / `/build-loop` without a coordinator-style post-ship review; (2) Path B MUST NOT be invoked when `Agent` is actually available ("Agent was slow" is not a valid reason); (3) Path B MUST NOT substitute for Codex review on `cross-system-review`-labeled issues; (4) the fallback MUST NOT be satisfied by an out-of-harness channel (custom API script, separate Claude terminal / web chat, local LLM) — those skip the harness artifact contract.

### 7. Create PR
- Push branch: `git push -u origin HEAD`
- Create PR via `gh pr create` with summary and test plan
- Link the Linear issue in PR body

### 8. Wait for CI
- `gh pr checks <pr-number> --watch`. If CI fails, fix and push — do not merge red. Branch protection blocks merge (normal users + admins) on any red required check (`python / test`, `web / test`, `visual-regression / visual`, `visual-gate-scope / scan`, `coverage-table-scan / scan`).

### 9. Merge and sync
- Before `gh pr merge`, verify the latest CI run on `main` is green **and its `headSha` matches current main HEAD** (`gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'`). Retry up to 3× with 10s delay on stale-SHA. Do not batch-merge.
- Merge: `gh pr merge <pr-number> --squash --delete-branch`. Sync: `git checkout main && git pull`. Update Linear issue to Done via `mcp__linear__save_issue`.

### Rollback and emergency bypass

- **Rollback**: `git revert <merge-sha>` (new commit, never rewrite history), push, open fix PR, reopen the Linear issue to In Progress.
- **Emergency admin bypass** (infrastructure outage only, not code test failures): `gh pr merge --admin` or GitHub UI "Merge without waiting for requirements" — MUST include `## Admin-merge disclosure` per the NEVER-list rule (full contract in `.claude/rules/merge-discipline.md` § "Admin-merge disclosure").

## Conventions

- **Commit prefixes**: `<linear-id>:` (e.g., `S5U-724:`) referencing the Linear issue
- **Config format**: TOML for all pipeline/document configuration
- Path-specific conventions (Python, TypeScript, extraction, schemas, web, hooks, visual-verify, CI guards, merge discipline) are in `.claude/rules/` — auto-loaded on path match.
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
- **Never skip pre-commit hooks without disclosure** (S5U-629). Covers `git commit --no-verify` / `-n`, env-var bypasses (`HUSKY=0`, `LEFTHOOK=0`, `SKIP=`, `HOOK_BYPASS=`, `NO_VERIFY=`, `COORDINATOR_ACK_STATUS_SOURCE=`), direct `.git/hooks` mutation (`chmod -x`, `rm`, no-op replacement), and `core.hooksPath` redirection. If you used any of these — **even if the commit was rolled back before reaching `origin`** — add a level-2 `## Hook bypass disclosure` heading to the PR body naming the commit SHA, the reason, and independent verification of the skipped check(s). Concealment grades stronger than the bypass itself — an undisclosed bypass is CRITICAL. Full token list, rationale, and residuals in `.claude/rules/hooks.md` § "Hook-bypass disclosure"; reviewer probe in `.claude/prompts/review.md` check #22.
- **Never merge with admin-bypass without disclosure** (S5U-671). `gh pr merge --admin`, REST `PUT /repos/.../pulls/<N>/merge` with admin privileges, or GitHub UI "Merge without waiting for requirements" MUST be documented in the PR body under a level-2 `## Admin-merge disclosure` heading naming (a) the bypassed surface (required check, `strict: true`, CODEOWNERS, conversation resolution, signed commits, linear history), (b) why admin-merge was appropriate, (c) what the worker did to verify the bypassed surface independently. Applies to PRs opened after S5U-671 lands. Concealment grades stronger than the bypass itself — an undisclosed admin-bypass is CRITICAL regardless of whether the bypassed surface was truly benign. Full vector list, two-pass reviewer-probe semantics (required-check pass on PR HEAD SHA + token-grep pass), and stale-context carve-out history in `.claude/rules/merge-discipline.md` § "Admin-merge disclosure"; reviewer probe in `.claude/prompts/review.md` check #25.

## Context management

- On `/compact`, preserve: Linear issue ID, branch name, gate pass/fail state, architectural decisions, DoD checklist state, blockers.
- On long-session end, write `HANDOFF.md` at repo root (what worked / failed / current state / next). File is gitignored.
- `/compact` between task phases in the same issue; `/clear` when switching issues; `/context` to inspect token use.

## Current state

All work is tracked in Linear (project ATE1). Check `mcp__linear__list_issues(project="ATE1")` for current status.

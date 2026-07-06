# AGENTS.md

Primary AI entrypoint for `aeon-trespass-expert`. Load the relevant `.ai-run/guides/` file before changing code. `CLAUDE.md` is a Claude Code shim importing this file — plus a **machine-scanned anchors** section (Commands, Quality gates, review contract) that fail-closed repo guards parse; those anchor sections in CLAUDE.md are the verbatim source of truth for what they cover.

## What this is

IR-first document compiler + static web reader for Aeon Trespass rulebook translation (EN→RU). Monorepo with two products:

- **apps/pipeline** — Python 3.12 content compiler (PDF → IR → translate → QA → site bundle)
- **apps/web** — React 19 / Vite static reader that renders the bundle

```
apps/pipeline/       Python pipeline (uv, pydantic, typer)
apps/web/            React 19 / Vite / React Router 7 (pnpm, Storybook)
packages/schemas/    Shared schemas: python/ (Pydantic) -> jsonschema/ -> ts/ (generated TS types)
configs/             TOML configs: documents, base, ci, glossary, symbols
scripts/             Codegen, fixture bootstrap, export utilities, CI guards
artifacts/           Pipeline output (gitignored run data)
docs/                Architecture docs (read on demand, not memorized)
```

## Guide Imports

<!-- ai-run-init:guide-imports start -->
AGENTS.md has no native import directive — the tables below are plain links; load the file at the listed path.

| Category | Guide Path | Purpose |
|---|---|---|
| Project context | .ai-run/guides/project.md | Identity, Linear ticket adapter, GitHub/PR adapter |
| Architecture | .ai-run/guides/architecture/architecture.md | System map: pipeline → export → reader, schema contract |
| Quality gates | .ai-run/guides/quality-gates.md | Exact lint/typecheck/test/visual commands, pass/fail shapes |
| Git workflow | .ai-run/guides/standards/git-workflow.md | Branch/commit/merge conventions with real S5U examples |
| Development workflow | .ai-run/guides/standards/development-workflow.md | Linear loop, definition of done, review + disclosure contracts |

| Module | Guides |
|---|---|
| apps/pipeline | apps/pipeline/.ai-run/guides/ (architecture, testing, development) |
| apps/web | apps/web/.ai-run/guides/ (architecture, testing, development) |
| packages/schemas | packages/schemas/.ai-run/guides/ (development/schema-codegen) |
<!-- ai-run-init:guide-imports end -->

## Task Classifier

<!-- ai-run-init:task-classifier start -->
| Category | User Intent | Example Requests | P0 Guide | P1 Guide |
|---|---|---|---|---|
| Pipeline change | Modify extraction/translation/QA stages | "fix reading order on p42" | apps/pipeline/.ai-run/guides/architecture/architecture.md | apps/pipeline/.ai-run/guides/development/development-practices.md |
| Web change | Reader UI, routes, rendering | "add glossary tooltip" | apps/web/.ai-run/guides/architecture/architecture.md | apps/web/.ai-run/guides/development/development-practices.md |
| Schema change | IR/bundle shape, generated types | "add field to PageIR" | packages/schemas/.ai-run/guides/development/schema-codegen.md | .ai-run/guides/architecture/architecture.md |
| Testing | Write/fix tests, flaky CI | "add test for planner" | module testing guide (apps/*/.ai-run/guides/testing/testing-patterns.md) | .ai-run/guides/quality-gates.md |
| Ship / git | Commit, PR, merge, revert | "ship it" | .ai-run/guides/standards/git-workflow.md | .ai-run/guides/standards/development-workflow.md |
| Cross-system / ADR | Refactors spanning pipeline+web, IR shape | "change block model" | .ai-run/guides/architecture/architecture.md | docs/PROJECT_ARCHITECTURE.md |
<!-- ai-run-init:task-classifier end -->

## Critical Rules

<!-- ai-run-init:critical-rules start -->
| Rule | Trigger | Action |
|---|---|---|
| Check Guides First | ANY task | Match request to category and load the P0 guide before searching broadly |
| Path rules | Editing files under a path with a `.claude/rules/*.md` match | Follow that rules file — `.claude/rules/` stays authoritative over guides |
| Testing | "write tests" / "run tests" | Only when requested or needed for verification; red-before evidence per `.claude/rules/hooks.md` |
| Git Operations | "commit" / "push" / "PR" | Only then; load `.ai-run/guides/standards/git-workflow.md` |
| Workflow | Any tracked change | Follow `.ai-run/guides/standards/development-workflow.md` (Linear-driven, review before PR) |
| Shell | ANY shell command | bash/Linux syntax; use `uv run` / `pnpm` wrappers, never bare `mypy`/`pytest`/`tsc` |
<!-- ai-run-init:critical-rules end -->

## Commands

<!-- ai-run-init:commands start -->
| Need | Source Guide | Source Evidence | Notes |
|---|---|---|---|
| Lint / format / typecheck | .ai-run/guides/quality-gates.md | Makefile, pyproject.toml, apps/web/package.json | Load guide before running |
| Tests (fast vs full vs visual) | .ai-run/guides/quality-gates.md | Makefile, .claude/hooks/pre-commit-check.sh, CI workflows | Load guide before running |
| Codegen / export | .ai-run/guides/quality-gates.md + packages/schemas/.ai-run/guides/development/schema-codegen.md | Makefile | Run after any Pydantic model change |
| Git / review workflow | .ai-run/guides/standards/git-workflow.md | git history, CLAUDE.md anchors | Load guide before git operations |
<!-- ai-run-init:commands end -->

## Development workflow (MANDATORY)

All work is tracked in **Linear** (project **ATE1**, team **S5U**); every change follows the issue → branch → gates → fresh-eyes review → PR → green CI → squash-merge loop in `.ai-run/guides/standards/development-workflow.md`. The independent review contract (Path A/B selection, safety-gate escalation via `/coordinator`, coordinator-ack) is machine-anchored in `CLAUDE.md` § "Independent fresh-eyes review" — read it before any PR. Quality-gate meaning: local green = safe to push; CI green (all required checks) = definition of done.

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

## Conventions

- **Commit prefixes**: `<linear-id>:` (e.g., `S5U-724:`) referencing the Linear issue
- **Config format**: TOML for all pipeline/document configuration
- Path-specific conventions (Python, TypeScript, extraction, schemas, web, hooks, visual-verify, CI guards, merge discipline) are in `.claude/rules/` — auto-loaded on path match and authoritative
- **Linear issue conventions**: read `.claude/prompts/linear-conventions.md` before creating or updating Linear issues
- **Scripts before skills**: before invoking a slash-command skill for batch or multi-step work, check `scripts/` for a purpose-built tool (e.g., `scripts/run-issues.sh` for batch issue runs — use this instead of `/build-loop`)
- **Translation provider switching** (S5U-748): see `docs/specs/translation-providers.md` for the `gemini-cli` ↔ `codex-cli` switch and the opt-in Codex CLI smoke command (`-m codex_live` + `ATR_CODEX_LIVE_SMOKE=1`)

## Context management

- On `/compact`, preserve: Linear issue ID, branch name, gate pass/fail state, architectural decisions, DoD checklist state, blockers.
- On long-session end, write `HANDOFF.md` at repo root (what worked / failed / current state / next). File is gitignored.
- `/compact` between task phases in the same issue; `/clear` when switching issues; `/context` to inspect token use.

## Current state

All work is tracked in Linear (project ATE1). Check `mcp__linear__list_issues(project="ATE1")` for current status.

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
make lint             # ruff check + mypy + import-linter + file-length + pnpm lint
make typecheck        # mypy + tsc
make test             # All tests (pytest + pnpm test)
make codegen          # Regenerate JSON Schema + TS types from Pydantic models
make export           # Export pipeline artifacts to web public (re-generates documents/)
make format           # Auto-fix formatting (ruff format + ruff check --fix + pnpm format)
make clean            # Remove caches and build artifacts
```

## Quality gates

Two tiers of checks run at different stages. Both must pass.

### Local (pre-commit hook, 8 gates)

Runs automatically on every `git commit` via `.claude/hooks/pre-commit-check.sh`. Fast — targets < 60 s.

1. `ruff check` — lint (includes McCabe complexity C901, max 12)
2. `ruff format --check` — format violations
3. `mypy --strict` — type errors
4. `lint-imports` — import layer contracts (no cyclic dependencies)
5. `check_file_length.py` — max 400 lines per source file
6. `eslint` — frontend lint (`import/no-cycle`, `max-lines: 400`)
7. `tsc --noEmit` — frontend type check
8. `pytest -x -q --timeout=60 -m "not slow"` — fast test subset only

### CI (GitHub Actions, 8 + 4 extra)

Runs on every push to `main` and on every PR. Includes all 8 local gates plus:

9. `check_codegen_fresh.sh` — verifies generated JSON Schema + TS types match Pydantic sources. *CI-only because it needs `pnpm install` and a clean checkout to be reliable.*
10. `validate_fixture_manifest.py` — fixture integrity checks. *CI-only because it can be slow with large fixture sets.*
11. `check_extraction_scope.py` — detects extraction-related changes in PRs. *CI-only because it compares against the PR base branch.*
12. `check_golden_refresh.py` — validates golden file updates when extraction scope is detected. *CI-only because it requires base-branch comparison and only triggers conditionally.*

CI also runs `pytest --tb=short` (full suite — includes slow tests, no timeout), unlike the pre-commit fast subset.

### What "passing" means

- **Local green** = safe to commit and push, but not sufficient for merge.
- **CI green** = all 12 gates pass — required for merge. "Definition of Done" means CI green.

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

### 3. Work on the branch
- Commit early and often with prefix `S5U-XXX: description`
- The 8 local gates run automatically before each commit via hook

### 4. Definition of done (all must be true before PR)
- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] Local gates pass: `make lint && make typecheck && make test`
- [ ] CI green after push (all 12 gates — local green alone is not sufficient)

### 5. Sub-agent code review (MANDATORY before PR)
- **You MUST spawn a review agent before creating a PR.** This is not optional.
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- If the review agent says **BLOCK**, fix the issues before proceeding
- If only warnings/nits, use judgement — fix warnings, nits are optional

### 6. Create PR
- Push branch: `git push -u origin HEAD`
- Create PR via `gh pr create` with summary and test plan
- Link the Linear issue in PR body

### 7. Wait for CI
- Check CI status: `gh pr checks <pr-number> --watch`
- If CI fails, fix and push — do not merge with red CI

### 8. Merge and sync
- Merge via: `gh pr merge <pr-number> --squash --delete-branch`
- Sync local: `git checkout main && git pull`
- Update Linear issue to **Done**: `mcp__linear__save_issue(id="S5U-XXX", state="Done")`

### Rollback process
If a merged PR breaks something:
1. Identify the merge commit: `git log --oneline main`
2. Revert it: `git revert <commit-sha>` (creates a new commit, does NOT rewrite history)
3. Push the revert, open a new PR for the fix
4. Reopen the Linear issue and set back to **In Progress**

## Conventions

- **Commit prefixes**: `S5U-XXX:` referencing the Linear issue
- **Config format**: TOML for all pipeline/document configuration
- Path-specific conventions (Python, TypeScript, extraction, schemas) are in `.claude/rules/` — loaded automatically when touching matching paths

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

## Current state

All work is tracked in Linear (project ATE1). Check `mcp__linear__list_issues(project="ATE1")` for current status.

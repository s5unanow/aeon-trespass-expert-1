# AGENTS.md — Aeon Trespass Expert

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
make lint             # ruff check + mypy + pnpm lint
make typecheck        # mypy + tsc
make test             # All tests (pytest + pnpm test)
make codegen          # Regenerate JSON Schema + TS types from Pydantic models
make format           # Auto-fix formatting (ruff format + ruff check --fix + pnpm format)
make clean            # Remove caches and build artifacts
```

## Quality gates (must pass before commit)

1. `ruff check` — no lint errors (includes McCabe complexity C901, max 12)
2. `ruff format --check` — no format violations
3. `mypy --strict` — no type errors
4. `lint-imports` — Python import layer contracts (no cyclic dependencies)
5. `check_file_length.py` — max 400 lines per source file
6. `pytest` — all tests pass
7. `eslint` — frontend lint (includes `import/no-cycle`, `max-lines: 400`)
8. `tsc --noEmit` — frontend type check

CI runs gates 1-8 on every push. Pre-commit hook enforces them automatically.

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
- Quality gates (ruff, mypy, lint-imports, file-length, eslint, tsc, pytest) run automatically before each commit via hook

### 4. Definition of done (all must be true before PR)
- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] No new `except Exception` without structured logging
- [ ] Full checks pass: `make lint && make typecheck && make test`

### 5. Sub-agent code review (MANDATORY before PR)
- **You MUST spawn a review agent before creating a PR.** This is not optional.
- Read `.Codex/prompts/review.md` and use it as the Agent prompt
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
- **Never** use `git reset --hard` or `git push --force` on main

## Conventions

- **Commit prefixes**: `S5U-XXX:` referencing the Linear issue
- **Contract direction**: Python Pydantic -> JSON Schema -> TypeScript (never manual TS types)
- **Config format**: TOML for all pipeline/document configuration
- **JSON IO**: Use orjson with atomic writes (temp + rename) where applicable

## Current state

All work is tracked in Linear (project ATE1). Check `mcp__linear__list_issues(project="ATE1")` for current status.

# Project Context

**Project name:** aeon-trespass-expert  
**Repository:** [github.com/s5unanow/aeon-trespass-expert-1](https://github.com/s5unanow/aeon-trespass-expert-1)  
**Project code:** ATE1 (Linear)  
**Team prefix:** S5U  

## What this is

IR-first document compiler + static web reader for Aeon Trespass rulebook translation (EN→RU). Monorepo: Python 3.12 pipeline (`apps/pipeline`, uv) + React 19 web reader (`apps/web`, pnpm). Shared schemas in `packages/schemas/` (Pydantic → JSON Schema → TypeScript codegen).

## Tracker

**Provider:** Linear  
**Project:** ATE1  

**Lookup** (fetch issue):
```
mcp__linear__get_issue(id="S5U-NNNN")
```

**Create / update** (save issue):
```
mcp__linear__save_issue(...)
```

**List** (pick backlog issues):
```
mcp__linear__list_issues(project="ATE1", state="Backlog")
```

**Label conventions** (required):
- **Area:** Pipeline, Reader, DevOps, Config, QA, Testing
- **Type:** Bug, Regression, Feature, Improvement, Refactor
- **Modifier (optional):** cross-system-review (triggers Codex review in `/ship`)

## Source control

**Hosting:** GitHub  
**Default branch:** main  
**Protected:** Yes (branch protection: 5 required checks + status: strict + dismiss stale reviews)  

**Clone:**
```bash
git clone https://github.com/s5unanow/aeon-trespass-expert-1.git
cd aeon-trespass-expert-1
make bootstrap  # uv sync + pnpm install
```

## Ticket-to-branch adapter

All work maps 1:1 to Linear issues. No free-form branches.

| Step | Command / Link |
|------|----------------|
| Create/assign | Linear UI (project ATE1) or `mcp__linear__save_issue` |
| Read issue | Linear issue ID → fetch via `mcp__linear__get_issue("S5U-NNNN")` |
| Branch | `git checkout -b s5unanow/s5u-NNNN-short-description` (from CLAUDE.md line 87) |
| Commit | `git commit -m "S5U-NNNN: description"` (prefix required) |
| PR | `gh pr create --title "..." --body "..."` (link Linear issue in body) |
| Merge | `gh pr merge <N> --squash --delete-branch` (squash-merge only) |
| Mark done | `mcp__linear__save_issue(id="S5U-NNNN", state="Done")` |

## Definition of done (before PR)

- [ ] Code change addresses Linear issue description
- [ ] New/changed code has tests (unless pure config/docs)
- [ ] New tests have red-before evidence (see `.claude/rules/hooks.md` § "Three-input test discipline")
- [ ] Coverage table included if ≥3 bullets (see `.claude/prompts/linear-conventions.md` § "Coverage table format")
- [ ] No tech debt / temporary code / TODO shortcuts remain
- [ ] Local gates pass: `make check`
- [ ] Pre-PR review complete (path A if Agent available; path B if not — disclose in PR)
- [ ] CI green (all 18 gates pass — required for merge)

## Repository structure

```
apps/pipeline/              Python 3.12 pipeline (uv)
  src/atr_pipeline/         Main package
  tests/                    Unit + integration tests
apps/web/                   React 19 / Vite static reader (pnpm)
  src/components/           React components
  tests/e2e/                Playwright visual regression
packages/schemas/
  python/                   Pydantic models (source of truth)
  jsonschema/               Generated JSON Schema
  ts/                       Generated TypeScript types
configs/                    TOML: documents, base, ci, glossary, symbols
scripts/                    Codegen, export, CI guards
.claude/                    Hooks, prompts, rules, skills
```

## Key commands

```bash
make bootstrap              # Install all deps
make check                  # Full local gate (lint + typecheck + test)
make lint                   # Ruff + mypy + import-linter + file-length + fixtures + codegen
make format                 # Auto-fix ruff + pnpm
make typecheck              # mypy + tsc
make test                   # pytest + pnpm test
make codegen                # Regenerate schemas from Pydantic
make check-codegen          # Verify codegen freshness
make export                 # Export pipeline artifacts to web
make verify-branch-protection  # Audit live main protection
make validate-fixtures      # Fixture manifest check
```

See `Makefile` for all 20+ targets.

## CI gates location

All CI workflows in `.github/workflows/`. Required-check contexts in branch protection:
- `python / test` — pytest
- `web / test` — pnpm test
- `visual-regression / visual` — Playwright snapshots
- `visual-gate-scope / scan` — Baseline-update guard
- `coverage-table-scan / scan` — Coverage table enforcement

See `CLAUDE.md` lines 39–71 and `quality-gates.md` for full gate details.

## Merge discipline

**Commit signature:** Optional (no enforced GPG)  
**Branch protection:**
  - Require PR reviews: 0 (review is human-based; no mechanical gate)
  - Require status checks: ✓ 5 contexts (see above)
  - Require conversation resolution: ✗
  - Dismiss stale reviews: ✓
  - Enforce admins: ✓ (no bypass except emergency, with disclosure)

**Merge pre-flight (step 9):**
```bash
# Verify main CI is green and HEAD is latest
gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'
# Merge with squash
gh pr merge <N> --squash --delete-branch
```

**Emergency admin-bypass:** Allowed only for infrastructure outage (not test failures). **Requires disclosure** in PR body under `## Admin-merge disclosure` heading (see `.claude/rules/merge-discipline.md`).

## Cost of work

No tier system. All work runs through `.ai-run/` harness if agents are involved. Human workers use `make` + `gh` CLI directly.

## Notes

- **No rollbacks via git reset.** Use `git revert` (new commit) for merge unwinding.
- **No force-push to main.** Ever.
- **Pre-commit hook enforced.** Blocks commits that fail local gates; cannot be bypassed silently (disclosure required if disabled).
- **Safety-gate PRs escalated.** Any PR touching hooks / CI checks / branch protection must ship via `/coordinator`, not `/ship` / `/next` / `/build-loop`. Coordinator spawns post-ship fresh-eyes reviewer.
- **Cross-system review.** Issues labeled `cross-system-review` get a second (Codex) review in `/ship` workflow.

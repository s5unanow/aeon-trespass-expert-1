# AGENTS.md — Aeon Trespass Expert (SDLC Factory Entrypoint)

**For comprehensive project documentation, see [`CLAUDE.md`](CLAUDE.md).**

This file is the SDLC Factory entrypoint for the aeon-trespass-expert monorepo. It imports factory-owned guides under `.ai-run/guides/` and routes agents to authoritative documentation per task type.

## Quick Reference

| Need | Resource |
|---|---|
| **Project identity & tracker** | [`.ai-run/guides/project.md`](.ai-run/guides/project.md) |
| **Git workflow & conventions** | [`.ai-run/guides/standards/git-workflow.md`](.ai-run/guides/standards/git-workflow.md) |
| **Quality gates & commands** | [`.ai-run/guides/quality-gates.md`](.ai-run/guides/quality-gates.md) |
| **Comprehensive docs** | [`CLAUDE.md`](CLAUDE.md) (project overview, architecture, development workflow, NEVER rules, safety-gate discipline) |
| **Path-specific rules** | [`.claude/rules/`](.claude/rules/) (pipeline, web, extraction, schemas, visual-verify, hooks, merge-discipline, guards) |
| **Custom workflows** | [`.claude/skills/`](.claude/skills/) (build-loop, ship, coordinator, next, preflight, revert, codex-review) |

## Task Router

Use this table to find the right documentation for your task:

<!-- start:managed:task-router -->

| Task type | Documentation | CLI command or skill | Notes |
|---|---|---|---|
| **Pick up an issue** | `CLAUDE.md` §1 + `.ai-run/guides/project.md` | (No CLI; use Linear UI or `mcp__linear__list_issues`) | Auto-pick highest-priority Backlog issue; mark In Progress |
| **Create a feature branch** | `.ai-run/guides/standards/git-workflow.md` § "Branch naming" | `git checkout main && git pull && git checkout -b s5unanow/s5u-NNNN-short-description` | Hook enforces pattern; direct commits to main blocked |
| **Run quality gates locally** | `.ai-run/guides/quality-gates.md` | `make check` (aggregate) or `make lint / typecheck / test` | Pre-commit hook runs gates 0–8 automatically; fails if not passing |
| **Commit code** | `.ai-run/guides/standards/git-workflow.md` + `CLAUDE.md` §5 | `git commit -m "S5U-NNNN: description"` | Prefix required; hook runs 9 local gates; fails if any gate fails |
| **Push and open PR** | `CLAUDE.md` §7 + `.ai-run/guides/standards/git-workflow.md` § "Workflow steps" | `git push -u origin HEAD` then `gh pr create --title "S5U-NNNN: ..." --body "..."` | Link Linear issue in PR body; title format required by hook |
| **Review changes** | `CLAUDE.md` §6 + `.claude/prompts/review.md` | (Path A) spawn independent review agent OR (Path B) inline self-review | Path determined by whether `Agent` tool is in direct tool list; output goes to `tmp/review-s5u-<N>.md` |
| **Wait for CI** | `.ai-run/guides/quality-gates.md` § "What passing means" | `gh pr checks <pr-number> --watch` | All 18 gates must pass (9 local + 9 CI); branch protection blocks merge if any red |
| **Merge PR** | `CLAUDE.md` §9 + `.ai-run/guides/standards/git-workflow.md` § "Merge & admin-bypass disclosure" | `gh pr merge <pr-number> --squash --delete-branch` | Verify main CI is green before merge; update Linear issue to Done |
| **Rollback on emergency** | `CLAUDE.md` § "Rollback and emergency bypass" | `git revert <merge-sha>` → push fix PR → reopen Linear issue | Never use `git reset --hard` or `git push --force`; use revert commits |

<!-- end:managed:task-router -->

## Quality Gates Summary

<!-- start:managed:quality-gates-summary -->

**18 total gates** (9 local + 9 CI):

### Pre-commit gates (run on `git commit`, <60s)
0. Secret guard (blocks .env, *.key, sk-, AKIA, ghp_, gho_, PEM)
1. Ruff check (lint + McCabe C901 ≤12)
2. Ruff format (format violations)
3. Mypy strict (type errors)
4. Import-linter (no cycles)
5. File-length (max 400 lines)
6. Oxlint (frontend lint)
7. Tsc (frontend typecheck)
8. Pytest fast (no slow tests)

### CI gates (run on push/PR, all must pass for merge)
9. Codegen freshness
10. Fixture manifest
11. Extraction scope (informational)
12. Golden refresh
13. Visual regression (Playwright, 0.5% pixel tolerance)
14. Visual-gate-scope scan
15. Coverage-table scan (≥3-bullet issues)
16. Instruction drift (CLAUDE.md/rules parity)
17. Make-doc parity (Makefile/CLAUDE.md)
18. Pytest full (all tests including slow)

**Commands:**
- Local green: `make check` (lint + typecheck + test)
- Pre-push check: `make lint && make typecheck && make test`
- CI gates: run automatically on `git push` to any branch

**What passing means:**
- **Local green:** safe to push, but NOT sufficient for merge
- **CI green:** all 18 gates pass; required for merge (definition of done)

See [`.ai-run/guides/quality-gates.md`](.ai-run/guides/quality-gates.md) for exact commands, pass/fail signals, auto-fix, and skip conditions.

<!-- end:managed:quality-gates-summary -->

## Project Identity

<!-- start:managed:project-identity -->

| Field | Value |
|---|---|
| **Project name** | aeon-trespass-expert |
| **Repository** | github.com/s5unanow/aeon-trespass-expert-1 |
| **Project code** | ATE1 |
| **Team prefix** | S5U |
| **Tracker** | Linear (project ATE1, team S5U) |
| **Default branch** | main |
| **Merge strategy** | squash-merge |
| **Commit prefix** | S5U-NNNN: |
| **Branch pattern** | s5unanow/s5u-NNNN-short-description |
| **Python version** | 3.12 (uv workspace) |
| **JavaScript runtime** | React 19 + Vite (pnpm workspace) |

<!-- end:managed:project-identity -->

## Development Workflow (Mandatory)

All work is tracked in **Linear (project ATE1, team S5U)**. Follow this 6-step flow:

1. **Pick an issue** → linear list Backlog, mark In Progress
2. **Create a branch** → `git checkout -b s5unanow/s5u-NNNN-short-description`
3. **Code & commit** → prefix `S5U-NNNN:`, hook runs 9 local gates
4. **Push & PR** → `git push -u origin HEAD`, `gh pr create`, link Linear issue
5. **Wait for CI** → all 18 gates must pass (branch protection blocks merge if red)
6. **Merge & sync** → `gh pr merge --squash`, update Linear issue to Done

**See [`CLAUDE.md`](CLAUDE.md) for detailed workflow steps, review discipline (Path A/B), coordinator-ack requirements, and rollback procedures.**

## Safety-Gate Escalation (MANDATORY)

PRs that touch safety-gate scope (hooks, review gates, CI checks, merge guards, `.claude/skills/**/SKILL.md` edits) MUST be shipped via `/coordinator` skill, not `/ship` / `/next` / `/build-loop`.

- **Local review:** Path A (independent agent) or Path B (inline self-review) — see `CLAUDE.md` §6 for details
- **Pre-PR gate:** `pre-pr-check.sh` enforces `coordinator-ack` commit status from `.claude/coordinator-signers.txt`
- **Post-merge audit:** `.github/workflows/post-merge-coordinator-ack.yml` verifies coordinator-ack on main

See [`CLAUDE.md`](CLAUDE.md) §6 and [`.claude/rules/merge-discipline.md`](.claude/rules/merge-discipline.md) for full rationale.

## Key Rules (NEVER)

- **Never use `git reset --hard` or `git push --force` on main**
- **Never commit .env, credentials, API keys, or secrets**
- **Never write manual TypeScript types** — generate from Pydantic via `make codegen`
- **Never skip pre-commit hooks without disclosure** — see `.claude/rules/hooks.md` § "Hook-bypass disclosure" (S5U-629)
- **Never merge with admin-bypass without disclosure** — see `.claude/rules/merge-discipline.md` § "Admin-merge disclosure" (S5U-671)
- **Never commit directly to main** — use feature branches; hook blocks it
- **Never merge with failing CI** — all 18 gates must pass; branch protection enforces this

See [`CLAUDE.md`](CLAUDE.md) §NEVER for the full list with cross-references.

## Reference Index

| Category | Location |
|---|---|
| **Factory guides** | [`.ai-run/guides/`](.ai-run/guides/) (project.md, standards/git-workflow.md, quality-gates.md) |
| **Canonical docs** | [`CLAUDE.md`](CLAUDE.md) (project overview, workflow, quality gates, NEVER rules) |
| **Path-specific rules** | [`.claude/rules/`](.claude/rules/) (8 rule files: pipeline, web, schemas, extraction, hooks, visual-verify, merge-discipline, guards, AUDIT) |
| **Custom workflows** | [`.claude/skills/`](.claude/skills/) (7 skills: build-loop, ship, coordinator, next, preflight, revert, codex-review) |
| **Automation prompts** | [`.claude/prompts/`](.claude/prompts/) (review.md 25-check discipline, plan.md, linear-conventions.md, codex-review.md) |
| **Pre-commit hooks** | [`.claude/hooks/`](.claude/hooks/) (9-gate enforcement) |
| **Architecture & playbooks** | [`docs/`](docs/) (read on-demand; not memorized) |

## For Agents

Agents should:
1. Read `.ai-run/guides/` first for task routing, project identity, and quality gates
2. Read [`CLAUDE.md`](CLAUDE.md) for comprehensive workflow, safety-gate discipline, and NEVER rules
3. Read path-specific `.claude/rules/` files when touching Python, TypeScript, extraction, schemas, frontend, hooks, visual-verify, or merge discipline
4. Invoke `.claude/skills/` workflows directly (e.g., `/ship`, `/coordinator`, `/build-loop`, `/next`)
5. When reviewing code, use `.claude/prompts/review.md` 25-check discipline

---

**Last updated:** 2026-07-07  
**SDLC Factory:** Knowledge Foundation (autonomous eval run)  
**Canonical authority:** [`CLAUDE.md`](CLAUDE.md)

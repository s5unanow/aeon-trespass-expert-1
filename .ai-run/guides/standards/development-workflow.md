# Development Workflow

Every change follows the Linear-driven workflow below — no exceptions. Incorporated from CLAUDE.md (which remains the machine-scanned anchor for the safety-gate-scope enumeration and quality-gate counts). Deep rationale lives in `.claude/rules/` (hooks.md, merge-discipline.md, guards.md) and `.claude/prompts/review.md` — those files remain authoritative.

## The loop (one Linear issue at a time)

| Step | What | Detail |
|---|---|---|
| 1. Pick up | User-specified or highest-priority unassigned Backlog issue in project ATE1 | `mcp__linear__list_issues`; mark In Progress via `mcp__linear__save_issue` |
| 2. Branch | `s5unanow/s5u-<N>-<slug>` off fresh main | see `.ai-run/guides/standards/git-workflow.md` |
| 3. Plan | Cross-subsystem or safety-gate change → run `.claude/prompts/plan.md` → `tmp/plan-s5u-<N>.md` | single-subsystem non-gate changes skip planning; safety-gate plans must document adversarial scenarios |
| 4. Implement | Commit `S5U-<N>: ...`; 9 local gates run per commit via hook | tests first where possible; red-before evidence for every new test |
| 5. Definition of done | Checklist below, all true before PR | includes `make check` green |
| 6. Fresh-eyes review | MANDATORY before PR; Path A (spawn review agent with `.claude/prompts/review.md`, checks 1–25) if the Agent tool is available, else Path B inline self-review with disclosure | reviewer writes `tmp/review-s5u-<N>.md`; BLOCK → fix and re-review |
| 7. PR | `git push -u origin HEAD`; `gh pr create` linking the issue | pre-PR hook enforces the review artifact |
| 8. CI | `gh pr checks <n> --watch`; never merge red | all 18 CI gates required |
| 9. Merge & sync | squash-merge after verifying main's latest CI run is green on current HEAD; sync main; mark issue Done | no batch merges |

## Definition of done (before PR)

- Change addresses the Linear issue description; new/changed code has tests.
- Every new test has red-before evidence cited in commit/PR body (`.claude/rules/hooks.md` § "Three-input test discipline").
- Coverage table in the Linear issue when it has ≥3 bullets (`.claude/prompts/linear-conventions.md`).
- No task-created tech debt: re-read `git diff main...HEAD`; leftover TODOs, swallowed errors, or shortcuts are blockers unless linked to a follow-up issue.
- No NEVER-list violations (AGENTS.md § Critical rules).
- `make check` green locally; CI green after push.

## Safety-gate escalation

Any PR touching safety-gate scope (per CLAUDE.md — hooks, pre-commit checks, review gates, CI checks, merge guards, branch-protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits) MUST ship via `/coordinator`, which spawns an independent post-ship reviewer. Mechanical enforcement: `pre-pr-check.sh` requires a `coordinator-ack` commit status from a signer in `.claude/coordinator-signers.txt`; a post-merge audit workflow re-checks every push to main. Full mechanics: `.claude/rules/merge-discipline.md`.

Bypass clauses (must-refuse): no shipping safety-gate changes via lone-worker skills; no Path B review when the Agent tool is actually available; no out-of-harness review substitutes.

## Disclosure contracts

| Event | Required disclosure |
|---|---|
| Any pre-commit hook bypass (even rolled back) | `## Hook bypass disclosure` heading in PR body — SHA, reason, independent verification (`.claude/rules/hooks.md`) |
| Any admin/branch-protection bypass at merge | `## Admin-merge disclosure` heading — bypassed surface, why, independent verification (`.claude/rules/merge-discipline.md`) |

Concealment grades stronger than the bypass itself.

## Rollback

`git revert <merge-sha>` (never rewrite history), push, open a fix PR, reopen the Linear issue to In Progress. Emergency admin bypass is for infrastructure outages only and requires the admin-merge disclosure.

## Scripts before skills

Before invoking a slash-command skill for batch work, check `scripts/` for a purpose-built tool (e.g. `scripts/run-issues.sh N` for batch issue runs instead of `/build-loop`).

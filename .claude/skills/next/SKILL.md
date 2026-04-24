---
name: next
description: Pick up the next Linear issue. Use when user says "next issue", "keep going", or after finishing a ship.
---

# Pick up next issue

## 1. Query backlog

```
mcp__plugin_linear_linear__list_issues(project="ATE1", state="Backlog")
```

## 2. Select highest-priority issue

Pick order by priority: **1 (Urgent) → 2 (High) → 3 (Normal) → 4 (Low) → 0 (None)**. Within the same priority, sort by milestone target date ascending. Pick the first result.

Note: Linear returns priority as an integer where `0` means "no priority" — do not sort numerically ascending, or issues with no priority will be picked before Urgent.

- **Epics** (have sub-issues): skip, pick their highest-priority sub-issue instead
- **No backlog issues**: tell user "No backlog issues found in ATE1."

## 3. Get full details (if truncated)

```
mcp__plugin_linear_linear__get_issue(id="S5U-XXX")
```

## 3b. Load Linear conventions

Read `.claude/prompts/linear-conventions.md` — apply these conventions when updating or creating Linear issues.

## 4. Set In Progress

```
mcp__plugin_linear_linear__save_issue(id="S5U-XXX", state="In Progress")
```

## 5. Prepare branch

```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-<NUMBER>-<short-description>
```

Working tree must be clean (hook enforced). Stash if dirty.

## 6. Report and begin

Summarize: issue ID/title, priority, milestone, key requirements, files to modify. Then begin implementation.

## Execution mode

Complete the current issue fully before returning. The scope of `/next` is a single issue — pick it up, implement, ship, done.

1. Implement the issue (with tests)
2. Run preflight checks and fix until passing
3. Commit with `S5U-XXX:` prefix
4. Run `/ship` to complete the workflow

If any step fails after reasonable retries, log the error and stop — do not loop indefinitely.

## Safety-gate scope hard-stop (S5U-628 / S5U-647)

Before invoking `/ship`, run:

```bash
git diff --name-only main...HEAD
```

If any changed path matches safety-gate scope per CLAUDE.md (concrete paths: `.claude/hooks/**`, `.claude/prompts/review.md`, `.claude/prompts/codex-review.md`, `.github/workflows/**`, `.github/actions/**`, `.claude/skills/**/SKILL.md`, `scripts/check_*.{sh,py}`, `scripts/pre-*.{sh,py}`, or `CLAUDE.md` itself), **stop the skill immediately**. Do **not** proceed to `/ship`. Per CLAUDE.md step 6 and the must-refuse **Bypass clauses (must-refuse, S5U-614)**, safety-gate PRs MUST be shipped via `/coordinator`, which spawns a post-ship fresh-eyes reviewer in a new sub-agent context.

Tell the user: *"Safety-gate scope detected. `/next` cannot complete this issue safely — re-invoke via `/coordinator` so an independent reviewer runs against the merged diff."* Then exit.

**There is no user-override clause** (removed in S5U-647). The pre-PR hook (`pre-pr-check.sh`) also enforces this independently at `gh pr create` time.

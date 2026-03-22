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

Sort by: priority ascending (1=Urgent … 4=Low; 0=No priority sorts last), then milestone target date ascending. Pick the first result.

- **Epics** (have sub-issues): skip, pick their highest-priority sub-issue instead
- **No backlog issues**: tell user "No backlog issues found in ATE1."

## 3. Get full details (if truncated)

```
mcp__plugin_linear_linear__get_issue(id="S5U-XXX")
```

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

## Autonomous mode

You are running autonomously. Never pause for user confirmation — there is no user to respond. Complete the full workflow without stopping:

1. Implement the issue (with tests)
2. Run preflight checks and fix until passing
3. Commit with `S5U-XXX:` prefix
4. Ship: review → PR → CI → merge → update Linear to Done

If any step fails after reasonable retries, log the error and exit — do not wait for input.

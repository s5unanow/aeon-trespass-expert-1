---
name: next
description: Pick up the next Linear issue and start working. Use when the user says "next issue", "keep going", "work on something", or when you've just finished shipping and need to continue.
---

# Pick up next issue

Follow these steps exactly:

## 1. Query the backlog

```
mcp__plugin_linear_linear__list_issues(project="ATE1", state="Backlog")
```

## 2. Select the highest-priority issue

Sort the results by:
1. **Priority value** ascending (1=Urgent, 2=High, 3=Medium, 4=Low; treat 0=No priority as 5, i.e. sort last)
2. **Milestone target date** ascending (earliest milestone first)
3. Pick the first result after sorting

If the issue is an **Epic** (has sub-issues listed in description), skip it and pick its highest-priority sub-issue instead. Epics are tracking containers, not implementable work.

If no backlog issues exist, tell the user: "No backlog issues found in ATE1. Create issues in Linear or ask me to suggest next steps."

## 3. Get full issue details

If the issue description was truncated, fetch the full version:
```
mcp__plugin_linear_linear__get_issue(id="S5U-XXX")
```

## 4. Set status to In Progress

```
mcp__plugin_linear_linear__save_issue(id="S5U-XXX", state="In Progress")
```

## 5. Prepare the branch

```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-<NUMBER>-<short-description>
```

- Branch name MUST match pattern `s5unanow/s5u-<number>-<description>` (enforced by hook)
- Working tree MUST be clean before branching (hook will block otherwise)
- If working tree is dirty, stash or discard changes first, then branch

## 6. Report to the user

Output a brief summary:
- Issue ID and title
- Priority and milestone
- Key requirements from the description
- Any mentioned files to modify

Then begin implementation immediately.

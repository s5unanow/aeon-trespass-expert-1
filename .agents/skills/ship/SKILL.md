---
name: ship
description: Ship current work — review, PR, CI, merge, update Linear. Use when implementation is done and code is committed, or the user says "ship it", "create PR", "we're done", "merge it".
---

# Ship current work

Follow these steps in order. Stop immediately if any step fails.

## 0. Extract issue context

Get the Linear issue ID from the current branch name:
```bash
git branch --show-current
```
Branch pattern is `s5unanow/s5u-<NUMBER>-<description>`. Extract the `S5U-<NUMBER>` issue ID.

If you're on `main` or a branch without a valid issue ID, stop and tell the user.

## 1. Code review (MANDATORY)

Read `.claude/prompts/review.md` and use it as the prompt for a review sub-agent:

```
Agent(subagent_type="general-purpose", prompt=<contents of .claude/prompts/review.md>)
```

Based on the review verdict:
- **BLOCK** — Stop. Report the critical issues. Do NOT proceed to PR. Fix the issues first.
- **PASS WITH WARNINGS** — Proceed. Include warnings in the PR body.
- **PASS** — Proceed.

## 2. Push

```bash
git push -u origin HEAD
```

Never use `--force` or `-f`.

## 3. Create PR

```bash
gh pr create --title "S5U-XXX: <short title>" --body "<body>"
```

PR body must include:
- `## Summary` — 1-3 bullet points describing what changed
- `## Test plan` — checklist of how to verify
- Linear issue link: `Resolves [S5U-XXX](https://linear.app/s5una/issue/S5U-XXX/...)`
- Review verdict summary
- Footer: `Generated with [Claude Code](https://claude.com/claude-code)`

Title must be under 70 characters.

## 4. Wait for CI

```bash
gh pr checks <pr-number> --watch
```

- If CI passes — proceed to merge
- If CI fails — report the failures, do NOT merge. Fix and push again.
- If no CI checks are reported (e.g. config-only change) — proceed to merge

## 5. Merge

```bash
gh pr merge <pr-number> --squash --delete-branch
```

## 6. Sync local

```bash
git checkout main && git pull
```

## 7. Update Linear

```
mcp__plugin_linear_linear__save_issue(id="S5U-XXX", state="Done")
```

## 8. Report

Tell the user: "S5U-XXX shipped and merged. Issue marked Done."

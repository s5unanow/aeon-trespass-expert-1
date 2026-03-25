---
name: ship
description: Ship current work to main. Use when implementation is done and committed, or user says "ship it", "create PR", "merge it".
---

# Ship current work

Stop immediately if any step fails.

## 0. Extract issue context

```bash
git branch --show-current
```

Extract `S5U-<NUMBER>` from branch pattern `s5unanow/s5u-<NUMBER>-<description>`. Stop if on `main` or no valid issue ID.

## 1. Code review (MANDATORY)

Read `.claude/prompts/review.md` and use it as the Agent prompt. The review agent will save its output to `tmp/review-s5u-<NUMBER>.md`.

- **BLOCK** — stop, report issues, fix before proceeding. Delete the review artifact, fix issues, then re-run review.
- **PASS WITH WARNINGS** — proceed, include warnings in PR body
- **PASS** — proceed

A pre-PR hook will block `gh pr create` if the review artifact is missing or contains a BLOCK verdict.

## 2. Push

```bash
git push -u origin HEAD
```

Never use `--force` or `-f`.

## 3. Create PR

```bash
gh pr create --title "S5U-XXX: <short title>" --body "<body>"
```

PR body: `## Summary` (1-3 bullets), `## Test plan` (checklist), Linear issue link (`Resolves [S5U-XXX](...)`), review verdict, footer (`Generated with [Claude Code](...)`). Title under 70 chars.

## 4. Wait for CI

```bash
gh pr checks <pr-number> --watch
```

CI passes → merge. CI fails → fix and push. No checks → merge.

## 5. Merge and sync

```bash
gh pr merge <pr-number> --squash --delete-branch && git checkout main && git pull
```

## 6. Update Linear

```
mcp__plugin_linear_linear__save_issue(id="S5U-XXX", state="Done")
```

Report: "S5U-XXX shipped and merged. Issue marked Done."

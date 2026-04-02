---
name: revert
description: Revert and rollback merged work. Use when "revert commit", "rollback", "undo merge".
---

# Revert a merged commit

Stop immediately if any step fails.

## 0. Parse input and resolve target commit

The argument `<identifier>` is either a commit SHA or a PR number.

**PR number** (digits, optionally prefixed with `#`):

```bash
gh pr view <NUMBER> --json mergeCommit --jq '.mergeCommit.oid'
```

Stop if the PR was not merged or has no merge commit.

**Commit SHA** (7-40 hex characters):

```bash
git rev-parse --verify <sha>^{commit}
```

Stop if the SHA does not resolve: "Could not resolve commit `<sha>`."

Store the resolved full SHA as `TARGET_SHA`.

## 1. Precondition checks

All checks must pass before any mutation.

**1a. Working tree must be clean.**

```bash
git status --porcelain
```

If non-empty, stop: "Working tree is dirty. Stash or discard changes before reverting."

**1b. Checkout main and pull.**

```bash
git checkout main && git pull
```

**1c. Target commit must be on main.**

```bash
git branch --contains <TARGET_SHA>
```

If `main` is not in the output, stop: "Commit `<TARGET_SHA>` is not on main. Only main commits can be reverted."

**1d. Advisory: already-reverted check.**

Get the target commit's subject line:

```bash
SUBJECT=$(git log -1 --format='%s' <TARGET_SHA>)
git log --oneline main --grep="Revert \"$SUBJECT\""
```

If a match is found, warn: "This commit appears to already have been reverted. Proceed anyway?" Wait for user confirmation. This is advisory, not a hard block.

## 2. Extract issue context

```bash
git log -1 --format='%s' <TARGET_SHA>
```

The commit subject follows `S5U-XXX: description (#NNN)`. Extract:

- `ISSUE_ID` — the `S5U-XXX` portion (regex: `S5U-[0-9]+`)
- `ISSUE_NUMBER` — the numeric part (e.g., `465`)
- `PR_NUMBER` — the `(#NNN)` suffix if present
- `COMMIT_SUBJECT` — the full subject line

If no `S5U-XXX` pattern is found, warn and use fallback branch name `s5unanow/revert-<short-sha>`. Linear reopening (step 11) will be skipped.

## 3. Create revert branch

```bash
git checkout -b s5unanow/s5u-<ISSUE_NUMBER>-revert
```

## 4. Execute the revert

```bash
git revert <TARGET_SHA> --no-edit
```

**If conflicts occur:**

```bash
# Capture conflicted files for the error message
git diff --name-only --diff-filter=U
git revert --abort
git checkout main
git branch -D s5unanow/s5u-<ISSUE_NUMBER>-revert
```

Stop: "Revert has conflicts in: `<file list>`. Manual resolution required."

## 5. Code review (mandatory)

Read `.claude/prompts/review.md` and use it as the Agent prompt. The review agent will save its output to `tmp/review-s5u-<ISSUE_NUMBER>.md`.

- **BLOCK** — stop, report issues, fix before proceeding. Delete the review artifact, fix, re-run review.
- **PASS WITH WARNINGS** — proceed, include warnings in PR body.
- **PASS** — proceed.

The pre-PR hook will block `gh pr create` if the review artifact is missing or contains a BLOCK verdict.

## 6. Push

```bash
git push -u origin HEAD
```

Never use `--force` or `-f`.

## 7. Create PR

```bash
gh pr create --title "Revert S5U-<ISSUE_NUMBER>: <short-desc>" --body "<body>"
```

PR body structure:

```
## Summary
- Reverts S5U-<ISSUE_NUMBER>: <COMMIT_SUBJECT>
- Original PR: #<PR_NUMBER>
- Reason: <user-provided reason, or "Rollback requested">

## Reverted commit
`<TARGET_SHA>`

## Review verdict
<verdict from step 5>

---
Reopens [S5U-<ISSUE_NUMBER>](https://linear.app/s5una/issue/S5U-<ISSUE_NUMBER>)

Generated with [Claude Code](https://claude.com/claude-code)
```

Title must be under 70 chars. Truncate description if needed.

## 8. Wait for CI

```bash
gh pr checks <pr-number> --watch
```

CI passes -> merge. CI fails -> investigate. A CI failure on a pure revert likely means the reverted code fixed a pre-existing issue. Report this to the user.

## 9. Check main CI status

Before merging, verify the latest CI run on `main` is green **and matches the current main HEAD**.

```bash
MAIN_SHA=$(gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha')
RUN_JSON=$(gh run list -b main --limit 1 --json headSha,status,conclusion,databaseId -q '.[0]')
RUN_SHA=$(echo "$RUN_JSON" | jq -r '.headSha')
```

**Step A — SHA match.** If `RUN_SHA` != `MAIN_SHA`, retry up to 3 times with 10 s delay. If still mismatched, stop: "No CI run found for current main HEAD."

**Step B — Evaluate:**
- `conclusion` = `"success"` -> proceed to merge.
- `status` = `"in_progress"` -> wait: `gh run watch <databaseId> --exit-status`.
- `conclusion` = `"failure"` -> stop: "Main CI is red. Fix main first or confirm override."

## 10. Merge and sync

```bash
gh pr merge <pr-number> --squash --delete-branch && git checkout main && git pull
```

## 11. Reopen Linear issue

```
mcp__plugin_linear_linear__save_issue(id="S5U-<ISSUE_NUMBER>", state="In Progress")
```

Report: "Reverted S5U-<ISSUE_NUMBER>. Issue reopened and set to In Progress. Revert PR: #<new-pr-number>."

If no Linear issue ID was extractable (step 2 fallback), skip this step.

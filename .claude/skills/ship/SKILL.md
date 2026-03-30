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

## 1b. Codex review (conditional on label)

Fetch the Linear issue if not already fetched in step 0/1:

```
mcp__plugin_linear_linear__get_issue(id="S5U-XXX")
```

Check the issue's labels for `cross-system-review`:

**Label ABSENT** → skip to step 2.

**Label PRESENT** →

1. Write marker file:
   ```bash
   mkdir -p tmp
   touch tmp/.codex-required-s5u-<NUMBER>
   ```
2. Read `.claude/prompts/codex-review.md` and follow its instructions (manages `codex exec`, REVISE loop, artifact)
3. If Codex reached **APPROVED** → proceed
4. If code changed during the REVISE loop, `tmp/review-s5u-<NUMBER>.md` is stale — delete it and re-run step 1 (Claude review). The Codex orchestration prompt handles the deletion; you re-run step 1.
5. If Codex did **not converge** (INCOMPLETE after 3 rounds) → **stop and ask user**. Do not proceed to push.

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

## 5. Check main CI status

Before merging, verify the latest CI run on `main` is green **and matches the current main HEAD** to prevent cascading failures from dispatch latency.

```bash
MAIN_SHA=$(gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha')
RUN_JSON=$(gh run list -b main --limit 1 --json headSha,status,conclusion,databaseId -q '.[0]')
RUN_SHA=$(echo "$RUN_JSON" | jq -r '.headSha')
```

**Step A — Verify SHA match.** If `RUN_SHA` ≠ `MAIN_SHA`, the latest run is stale (GitHub hasn't dispatched CI for the new HEAD yet). Retry up to 3 times with 10 s delay between attempts. If still mismatched after 3 retries, **stop and warn**: "No CI run found for current main HEAD — cannot verify CI status."

**Step B — Evaluate the matched run:**

- If `conclusion` is `"success"` → proceed to merge.
- If `status` is `"in_progress"` → wait for it to finish: extract `databaseId` and run `gh run watch <id> --exit-status`.
- If `conclusion` is `"failure"` → **stop and warn**: "Main CI is red — merging now would compound the failure. Fix main first or confirm override." Do not merge unless the user explicitly overrides.

## 6. Merge and sync

```bash
gh pr merge <pr-number> --squash --delete-branch && git checkout main && git pull
```

## 7. Update Linear

```
mcp__plugin_linear_linear__save_issue(id="S5U-XXX", state="Done")
```

Report: "S5U-XXX shipped and merged. Issue marked Done."

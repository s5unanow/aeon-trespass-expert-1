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

Read `.claude/prompts/linear-conventions.md` for issue convention context (labels, milestones, must-not-break).

## 1. Independent fresh-eyes code review (MANDATORY)

**Safety-gate scope hard-stop (S5U-628 / S5U-647):** before choosing the review path, run:

```bash
git diff --name-only main...HEAD
```

If any changed path matches safety-gate scope per CLAUDE.md (concrete paths: `.claude/hooks/**`, `.claude/prompts/review.md`, `.claude/prompts/codex-review.md`, `.github/workflows/**`, `.github/actions/**`, `.claude/skills/**/SKILL.md`, `scripts/check_*.{sh,py}`, `scripts/pre-*.{sh,py}`, or `CLAUDE.md` itself), **STOP `/ship` immediately**. Per CLAUDE.md step 6 ("Safety-gate scope escalation (MUST)") and the must-refuse bypass clause at CLAUDE.md:154, safety-gate PRs MUST be shipped via `/coordinator`, not `/ship`. Tell the user: *"Safety-gate scope detected (paths: ...). `/ship` cannot carry this safely because it has no post-ship fresh-eyes reviewer. Re-invoke via `/coordinator` so the coordinator spawns an independent reviewer sub-agent against the merged diff."* Then exit the skill. **There is no user-override clause at the skill level** — the previous override path (removed in S5U-647) reproduced the exact bypass S5U-628 was filed to close.

The pre-PR hook (`pre-pr-check.sh`) independently enforces this: it refuses `gh pr create` if the diff touches safety-gate scope and no `tmp/.coordinator-ack-<issue>` marker exists. Do not attempt to forge the marker — doing so is a hook-bypass-class event and must be disclosed in the PR body per the CLAUDE.md NEVER-list hook-bypass rule.

Review-path selection is driven by whether the `Agent` tool is in your direct tool list (see CLAUDE.md step 6 for the full rule):

### Path A — `Agent` tool available (top-level)

Spawn the review as an **independent** sub-agent. Read `.claude/prompts/review.md` and use it as the Agent prompt. Brief the reviewer with **only**:

- The Linear issue ID (e.g., `S5U-123`)
- The branch name and working directory
- An explicit reminder: "You are not the worker. Do not read any tmp/ artifacts authored by the worker (plans, scratch notes, PR drafts). Form your read of the diff from the Linear issue and `git diff main...HEAD` alone."

Do **NOT** paste into the brief: your own commit rationale, deviations list, PR draft body, summary of what you changed, or why a choice was made. Passing that framing anchors the reviewer on your interpretation and empirically produces false-PASS reviews (S5U-613). The reviewer reads the Linear issue and diff itself and probes the success criteria independently.

### Path B — `Agent` tool unavailable (sub-agent fallback, S5U-628)

Follow the maximum-independence inline self-review checklist in CLAUDE.md step 6: close draft notes, re-fetch the Linear issue, re-read the diff unanchored, walk all 24 checks in `.claude/prompts/review.md`, and write the same structured verdict artifact. Disclose the fallback in both the artifact and PR body. Do not use Path B if `Agent` is actually available; do not use Path B to bypass `/coordinator` escalation on safety-gate changes.

### Artifact + verdict (both paths)

The review output is saved to `tmp/review-s5u-<NUMBER>.md` with a structured `## Verdict` section containing `Verdict:`, `Critical:`, `Warning:`, `Suggestion:`, `Probes run:`, and `Bug IDs filed:` fields.

- **BLOCK** — stop, report issues, fix before proceeding. **Delete** the review artifact (it is now stale relative to the new HEAD), fix issues, then re-run review.
- **PASS WITH WARNINGS** — proceed, include warnings in PR body
- **PASS** — proceed

A pre-PR hook will block `gh pr create` if the review artifact is missing, lacks the structured `Verdict:` / `Probes run:` fields, lists fewer than 3 probe bullets, has a BLOCK verdict, or is older than the branch's HEAD commit (stale review).

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

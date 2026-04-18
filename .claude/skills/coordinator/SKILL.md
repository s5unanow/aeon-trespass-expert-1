---
name: coordinator
description: Orchestrate multi-issue runs by spawning worker + reviewer subagents per issue. Use when user says "run coordinator", "ship N issues with review", "batch with independent review", or wants a worker/reviewer separation beyond `/build-loop`.
---

# Coordinator flow

Orchestrate a batch of Linear issues through ship + independent review + bug triage. You (the coordinator) never write code — you spawn subagents, verify their work, and manage the queue.

## When to use this vs `/build-loop`

- **`/build-loop`**: the user pair-programs with you; you ship issues directly, checkpoint between them.
- **coordinator**: the user wants autonomy with a reviewer-in-the-loop. Workers ship; separate reviewers scrutinize against the Linear description and file bugs in Linear when they find gaps. Useful for stress-testing recent work or running through a large queue while building a bug log.

## Before starting — ask

1. **How many issues** to ship (default: 5)
2. **Linear filter** (default: Backlog, unassigned, project ATE1, priority order Urgent → High → Normal)
3. **Worker model** (default: Opus)
4. **Reviewer model** (default: Opus for safety-critical changes; Sonnet is cheaper first-pass and usable for simple work)
5. **On review-found bug**: (a) stop the run, (b) mark Urgent in Linear and continue — **default (b)**
6. **Second-pass Opus review** after a Sonnet first pass? (default: no, unless user explicitly wants two-pass)

Skip any question the user has already answered.

## The loop — sequential, one issue at a time

For each issue in the queue:

### 1. Spawn worker subagent
- `subagent_type: "general-purpose"`, `model: <worker_model>`
- Brief it with: Linear issue ID, working directory, full CLAUDE.md workflow obligations (plan if cross-system or safety-gate, branch, implement, local gates, mandatory sub-agent review per `.claude/prompts/review.md`, PR, CI, main-SHA verification, merge, sync, Linear → Done)
- Ask for a report ≤300 words: PR URL, merge SHA, CI pass summary, Linear confirmation, deviations, and — on failure — exact stop point + resume instructions

### 2. Verify inline (coordinator, no subagent)
- `git log --oneline -3 main` — confirm merge commit landed
- `gh pr view <N> --json state,mergeCommit,statusCheckRollup` — confirm MERGED + all required checks SUCCESS
- `mcp__plugin_linear_linear__get_issue` — confirm Linear status=Done

If any check fails, fix or abort — do not proceed to review as if shipped.

### 3. Spawn reviewer subagent
- `subagent_type: "general-purpose"`, `model: <reviewer_model>`
- **Preserve fresh eyes — pass only evidence, not worker narrative.** Include: merge SHA, PR URL, Linear issue ID, and the explicit reminder that the worker is NOT them. Do **NOT** pass the worker's report, rationale, commit messages, or their deviations list — these anchor the reviewer on the worker's framing and defeat the point of independent review. The reviewer must form its own read of the diff.
- Instruct:
  1. Fetch full Linear issue (description, success criteria, must-not-break, out-of-scope)
  2. `git show <sha>` — full diff; read changed files in full, not just hunks
  3. Probe each success criterion: is the behavior *actually* implemented, or just a file placeholder?
  4. Check NEVER-rule violations (handwritten TS, raw `print`, non-atomic writes, bare `except Exception`)
  5. Run targeted tests if cheap
  6. Emit a **structured severity-tagged verdict** (see output contract below)
- On BUG: file each distinct gap as a Linear issue via `mcp__plugin_linear_linear__save_issue`:
  - `team="S5una"`, `project="ATE1"`, `priority=1` (Urgent), `state=Backlog`
  - Title: `S5U-XXX follow-up: <defect>`
  - Body: **Gap**, **Evidence** (file:line), **Repro**, **Fix sketch**, **Link** (PR+SHA), and for second-pass: **Why first-pass missed**
  - Labels: `["Bug"]` plus any topical match

### Reviewer output contract

Reviewer returns the following fields explicitly so the coordinator can make a deterministic BLOCK / PROCEED decision without re-parsing prose:

- **Verdict**: one of `PASS` | `BUG`
- **Critical** (blocks the ship): list of `{title, evidence, linear_id_if_filed}` — success-criterion gaps, NEVER-rule violations, safety-gate bypasses, false-green tests
- **Warning** (ship OK, fix soon): list of same shape — correctness concerns that don't invalidate the claimed behavior
- **Suggestion** (nits, not filed): inline list — style, ergonomics, deferred scope
- **Probes run**: bullet list of what was actually verified (trust but verify — this exposes reviewer laziness)
- **Bug IDs filed**: flat list for the coordinator's final report

Coordinator rule: if any `Critical` item exists, the issue is logged as BUG regardless of whether it was filed as a new Linear issue (some criticals may be declined as "pre-existing, out of scope"). `Warning`-only → PASS with warnings noted in final report.

### 4. Apply bug policy
- Default (b): bugs are Urgent in Linear, run continues to next issue
- (a) variant: stop run, report to user, let them decide

### 5. Optional second-pass Opus review
If enabled, after a Sonnet first-pass PASS/BUG, spawn an Opus reviewer with the same brief plus:
- List of already-filed bugs (don't re-file)
- Explicit probe list appropriate to the change type (safety-gate = adversarial bypass probes, schema = contract direction, correctness-critical = end-to-end flow trace)
- Title bugs `S5U-XXX follow-up (second review): <defect>`

Opus second-pass consistently finds issues Sonnet misses, especially on safety gates and complex correctness paths.

## Failure handling

- **Worker stalls mid-task**: check branch/PR/Linear state yourself. If PR exists and CI passed, merge inline. If branch exists but no PR, spawn a small resume agent briefed with the exact state. If nothing pushed, spawn a fresh worker with the Linear issue state.
- **Worker reports unrecoverable failure**: report to user with the worker's own stop-point description. Do not silently retry.
- **Reviewer-filed bug blocks CI on main**: stop the queue, tell the user — running on a red main is wrong.
- **Queue exhausted before N reached**: report what shipped, what's still in Backlog, stop.

## Final report

At end of run:
- Table: issue | PR | merge SHA | review verdict (PASS / BUG → list IDs)
- Total merged, total bugs filed
- Observations: patterns across workers/reviewers (e.g., "3 of 5 cross-system issues produced bugs on first review; second-pass Opus caught 7 more gaps on top")
- Any process deviations noticed (worker skipped mandatory step, rule doc stale, etc.)

## Rules

- Sequential, never parallel — branches and Linear state race otherwise
- Never skip inline verification — a worker report is intent, not evidence
- Never delegate synthesis: you decide what's shipped, what's blocked, what to tell the user
- Keep task list (`TaskCreate`/`TaskUpdate`) accurate so progress is visible
- Match review depth to change class: safety-gate > correctness > feature > polish

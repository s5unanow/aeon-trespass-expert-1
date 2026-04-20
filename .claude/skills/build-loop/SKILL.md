---
name: build-loop
description: Autonomous development loop — pick up issues, implement, ship. Use when user says "build loop", "work autonomously", or "go through the backlog".
---

# Autonomous build loop

Work through Linear backlog issues one at a time until stopped.

## The loop

Repeat:

1. **Pick up & ship** — invoke `/next`, which handles the full single-issue lifecycle: select issue, branch, implement, preflight, commit, and ship
2. **Checkpoint** — after `/next` returns, pause and report to the user:
   - Show: issue ID, title, PR link, what was done
   - Ask: "S5U-XXX shipped. Continue to next issue?"
   - Yes/keep going → loop back to step 1
   - No/stop/no response → exit

**Important**: `/next` owns the single-issue scope (implement through ship). `/build-loop` owns the multi-issue loop and checkpoints between issues. Never skip the checkpoint — always pause between issues to let the user redirect or stop.

## Failure handling

- **No backlog issues**: Report "Backlog empty" and stop
- **Review BLOCK**: Fix, re-commit, re-review. After 3 blocks on same issue, ask user
- **CI failure**: Fix, push again. After 3 CI failures, ask user
- **Unclear issue**: Ask user before implementing — don't guess on architecture

## Rules

- Each cycle starts clean: main synced, fresh branch
- Never skip review, force-push, or force-merge
- Commit specific files, not `git add .`
- Ask the user at each checkpoint — don't run indefinitely

## Safety-gate scope hard-stop (S5U-628 / S5U-647)

`/build-loop` loops `/next`, which invokes `/ship` — all three run as lone workers without a coordinator-style fresh-eyes post-ship reviewer. Per CLAUDE.md step 6 and the must-refuse bypass clause at CLAUDE.md:154, safety-gate PRs (`.claude/hooks/**`, `.claude/prompts/review.md`, `.claude/prompts/codex-review.md`, `.github/workflows/**`, `.github/actions/**`, `.claude/skills/**/SKILL.md`, `scripts/check_*.{sh,py}`, `scripts/pre-*.{sh,py}`, `CLAUDE.md`) MUST be shipped via `/coordinator`, not `/build-loop`.

Before beginning each loop iteration, inspect the picked-up issue for safety-gate scope by:

1. Reading the Linear description for obvious safety-gate keywords (hooks, review gates, CI workflows, merge guards, SKILL.md, CLAUDE.md).
2. After branching + any exploratory edits, running `git diff --name-only main...HEAD` to catch diffs that landed on safety-gate paths.

If safety-gate scope is detected at either point, **stop the loop**. Tell the user: *"Next backlog issue is safety-gate-scoped — re-invoke via `/coordinator` for that issue."* Exit the loop cleanly. **There is no user-override clause** (removed in S5U-647). Also, `/next` and `/ship` each independently hard-stop, and the pre-PR hook (`pre-pr-check.sh`) blocks `gh pr create` if safety-gate scope is present without a `tmp/.coordinator-ack-<issue>` marker.

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

## Safety-gate scope warning (S5U-628)

`/build-loop` loops `/next`, which invokes `/ship` — all three run as lone workers without a coordinator-style fresh-eyes post-ship reviewer. Per CLAUDE.md step 6, safety-gate PRs (hooks, review prompts, CI workflows, merge guards, branch-protection-adjacent scripts, SKILL.md files) MUST be shipped via `/coordinator`, not `/build-loop`. If the next backlog issue is safety-gate-scoped, stop, warn the user, and recommend switching to `/coordinator` for that issue before resuming the loop.

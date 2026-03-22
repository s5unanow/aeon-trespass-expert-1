---
name: build-loop
description: Autonomous development loop — pick up issues, implement, ship. Use when user says "build loop", "work autonomously", or "go through the backlog".
---

# Autonomous build loop

Work through Linear backlog issues one at a time until stopped.

## The loop

Repeat:

1. **Pick up** — invoke `/next` to select and branch for the highest-priority backlog issue
2. **Implement** — read the issue, identify files, implement changes with tests following project conventions
3. **Preflight** — invoke `/preflight`; fix failures and re-run until all gates pass
4. **Commit** — `git add <specific files> && git commit -m "S5U-XXX: <description>"`
5. **Ship** — invoke `/ship` to review, PR, CI, merge, and update Linear
6. **Checkpoint** — ask: "S5U-XXX shipped. Continue to next issue?"
   - Yes/keep going → loop back to step 1
   - No/stop/no response → exit

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

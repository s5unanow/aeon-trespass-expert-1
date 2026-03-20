---
name: build-loop
description: Autonomous development loop — pick up issues, implement, and ship them one by one. Use when user says "build loop", "work autonomously", or "go through the backlog".
---

# Autonomous build loop

You are entering an autonomous development loop. Work through Linear backlog issues one at a time until stopped.

## The loop

Repeat the following cycle:

### Step 1: Pick up next issue

Follow the `/next` skill instructions:
1. Query Linear for highest-priority backlog issue in project ATE1
2. Sort by priority (Urgent first), then milestone target date (earliest first)
3. Skip epics — pick implementable sub-issues
4. Set issue to In Progress
5. Create branch from main: `s5unanow/s5u-<NUMBER>-<description>`

### Step 2: Implement

1. Read the issue description carefully — understand what needs to change and why
2. Identify the key files mentioned in the issue
3. Read existing code and tests to understand the current state
4. Implement the changes following project conventions:
   - Python: Pydantic models, structlog, type annotations, mypy --strict compatible
   - Frontend: React 19, TypeScript strict, generated types from schemas
   - Config: TOML format
5. Write tests for new/changed functionality (unless pure config/docs change)
6. No bare `except Exception` without structured logging

### Step 3: Preflight

Follow the `/preflight` skill instructions:
1. Run all 6 quality gates (ruff, mypy, eslint, tsc, pytest)
2. If any gate fails, fix the issue and re-run
3. Keep iterating until all gates pass

### Step 4: Commit

```bash
git add <specific files>
git commit -m "S5U-XXX: <description>"
```

Use descriptive commit messages with the issue prefix. Commit specific files, not `git add .`.

### Step 5: Ship

Follow the `/ship` skill instructions:
1. Spawn review agent (mandatory)
2. If BLOCK — fix issues, re-commit, re-review
3. If PASS — push, create PR, wait for CI, merge, sync main, update Linear to Done

### Step 6: Checkpoint

After shipping, ask the user:

> "S5U-XXX shipped and merged. Continue to next issue?"

- If **yes** or **keep going** — loop back to Step 1
- If **no** or **stop** — exit the loop
- If no response within the conversation — assume stop (don't loop forever)

## Failure handling

- **No backlog issues**: Report "Backlog empty — no more issues to pick up" and stop
- **Review BLOCK**: Fix the critical issues, re-commit, re-review. If blocked 3 times on the same issue, stop and ask the user for guidance.
- **CI failure**: Fix the failing tests/lint, push again. If CI fails 3 times, stop and ask the user.
- **Implementation unclear**: If the issue description is ambiguous or you're unsure about the approach, ask the user before implementing. Don't guess on architectural decisions.

## Important

- Each cycle starts clean: main is synced, fresh branch, no leftover state
- Never skip the review step — it's mandatory per CLAUDE.md
- Never force-push or force-merge
- Commit specific files, not everything
- Ask the user at each checkpoint — don't run indefinitely

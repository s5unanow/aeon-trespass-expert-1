---
description: Smoke-testing rules for shell commands and decision logic in hooks, prompts, and skills
globs: .claude/hooks/**,.claude/prompts/**,.claude/skills/**
---

- Every shell command added or modified must be smoke-tested in a clean shell (`bash -c "..."`) before committing — document the test in the commit message or PR
- Use toolchain wrappers — bare `mypy`, `pytest`, `ruff`, `oxlint`, `tsc` will fail in this repo:
  * Python: `uv run mypy`, `uv run pytest`, `uv run ruff`
  * JS: `pnpm lint`, `pnpm typecheck` (or `pnpm exec oxlint`, `pnpm exec tsc` for direct invocations)
- Any `if`/`grep`/pattern-match used for safety gating must be tested with at least three inputs:
  * Happy-path (should pass)
  * Failure input (should block)
  * Mixed/adversarial input (e.g., both PASS and BLOCK present)
- Any **new or modified** decision logic in a prompt or skill instruction that gates on a condition (e.g., "if the test file was added…", "if the CI run shows success…") must document at least three scenarios: happy-path (allows), failure input (blocks), adversarial edge (e.g., new function in old file, stale CI run for wrong commit)
- Include test commands as inline comments in the hook or as a companion test script

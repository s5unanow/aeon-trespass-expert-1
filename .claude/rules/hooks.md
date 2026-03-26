---
description: Smoke-testing rules for shell commands in hooks and prompts — applies to .claude/hooks/ and .claude/prompts/
globs: .claude/hooks/**,.claude/prompts/**
---

- Every shell command added or modified must be smoke-tested in a clean shell (`bash -c "..."`) before committing — document the test in the commit message or PR
- Use toolchain wrappers — bare `mypy`, `pytest`, `ruff`, `eslint`, `tsc` will fail in this repo:
  * Python: `uv run mypy`, `uv run pytest`, `uv run ruff`
  * JS: `pnpm exec eslint`, `pnpm exec tsc`
- Any `if`/`grep`/pattern-match used for safety gating must be tested with at least three inputs:
  * Happy-path (should pass)
  * Failure input (should block)
  * Mixed/adversarial input (e.g., both PASS and BLOCK present)
  * Include test commands as inline comments in the hook or as a companion test script

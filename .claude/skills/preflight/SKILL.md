---
name: preflight
description: Run all quality gates before committing. Use when about to commit, verifying code readiness, or checking if changes will pass CI.
---

# Preflight quality check

Run all 8 gates from repo root. Collect ALL results before reporting — do not stop at first failure.

## Output rules

- **Pass**: report only `✓ <gate> passed` — no full output
- **Fail**: show first 30 lines, note truncation count
- Skip frontend gates (7-8) if no frontend files changed

## Gates

1. `uv run ruff check apps/pipeline/src apps/pipeline/tests packages/schemas/python`
2. `uv run ruff format --check apps/pipeline/src apps/pipeline/tests packages/schemas/python`
3. `uv run mypy apps/pipeline/src packages/schemas/python`
4. `uv run lint-imports`
5. `uv run python scripts/check_file_length.py`
6. `uv run pytest -x -q --timeout=60 -m "not slow"`
7. `cd apps/web && pnpm lint`
8. `cd apps/web && pnpm typecheck`

## Reporting

Output a summary table (gate / PASS|FAIL / error count). For failures, include truncated output (≤30 lines).

- All pass → "All gates pass — ready to commit"
- Any fail → fix before committing
- Ruff format only → `uv run ruff format .` then re-check
- Ruff lint auto-fixable → `uv run ruff check --fix .` then re-check

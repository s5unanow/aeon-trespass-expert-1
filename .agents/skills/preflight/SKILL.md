---
name: preflight
description: Run all quality gates before committing. Use when you're about to commit, want to verify code readiness, or need to check if changes will pass CI.
---

# Preflight quality check

Run all 8 quality gates from the repo root. Collect ALL results before reporting — do not stop at the first failure.

## Gates to run

Run each gate and record pass/fail:

### 1. Ruff lint
```bash
uv run ruff check apps/pipeline/src apps/pipeline/tests packages/schemas/python
```

### 2. Ruff format
```bash
uv run ruff format --check apps/pipeline/src apps/pipeline/tests packages/schemas/python
```

### 3. Mypy (strict)
```bash
uv run mypy apps/pipeline/src packages/schemas/python
```

### 4. lint-imports
```bash
uv run lint-imports
```

### 5. File length check
```bash
uv run python scripts/check_file_length.py
```

### 6. Pytest (fast)
```bash
uv run pytest -x -q --timeout=60 -m "not slow"
```

### 7. ESLint (frontend)
```bash
cd apps/web && pnpm lint
```

### 8. TypeScript (frontend)
```bash
cd apps/web && pnpm typecheck
```

## Reporting

After running all gates, output a summary table:

```
Gate            Status   Notes
─────────────── ──────── ──────────────
Ruff lint       PASS/FAIL  (error count)
Ruff format     PASS/FAIL  (file count)
Mypy            PASS/FAIL  (error count)
lint-imports    PASS/FAIL  (error count)
File length     PASS/FAIL  (file count)
Pytest          PASS/FAIL  (passed/failed)
ESLint          PASS/FAIL  (error count)
TypeScript      PASS/FAIL  (error count)
```

For each failed gate, include the actual error output so you can fix the issues.

## Auto-fix hints

- If **only ruff format** fails: run `uv run ruff format .` then re-check
- If **only ruff lint** fails with auto-fixable rules: run `uv run ruff check --fix .` then re-check
- If **pytest** fails: read the test output carefully, fix the code, don't skip the test

## Important

- This does NOT commit anything — it's purely diagnostic
- Run from the repo root, not from a subdirectory
- If all gates pass, say "All gates pass — ready to commit"
- If any gate fails, fix the issues before committing
- Skip frontend gates (ESLint, TypeScript) if no frontend files were changed

# Code Quality Standards

**Python**: `ruff` (lint + format) + `mypy --strict` (`pyproject.toml`)
**TypeScript**: `oxlint` + `tsc --noEmit` (`apps/web/.oxlintrc.json`, `apps/web/tsconfig.json`)

---

## Quality Commands

| Action | Python | TypeScript |
|--------|--------|------------|
| Check all | `make lint` | `pnpm --filter @atr/web lint` |
| Lint | `uv run ruff check .` | `pnpm --filter @atr/web lint` (`oxlint --import-plugin .`) |
| Lint fix | `uv run ruff check --fix .` | — |
| Format check | `uv run ruff format --check .` | — |
| Format | `uv run ruff format .` | `pnpm --filter @atr/web format` (`prettier --write`) |
| Type check | `uv run mypy apps/pipeline/src packages/schemas/python` | `pnpm --filter @atr/web typecheck` (`tsc --noEmit`) |

**Before committing, run**: `make check` (aggregate: lint + typecheck + test). This also runs automatically as a subset via the pre-commit hook.

---

## Enforced Complexity/Length Rules

| Rule | Setting | Enforced by |
|------|---------|--------------|
| McCabe complexity | max 12 | ruff `C901` |
| Function parameters | max 7 | ruff `PLR0913` |
| Branches per function | max 12 | ruff `PLR0912` |
| Statements per function | max 50 | ruff `PLR0915` |
| Python file length | 400 lines | `scripts/check_file_length.py` |
| TS file length | 400 lines (blank/comments excluded) | `apps/web/.oxlintrc.json` `eslint/max-lines` |
| Import cycles | forbidden | ruff `I` rules (Python) / `import/no-cycle: error` (oxlint) |

Line length: 100 (`pyproject.toml` `[tool.ruff]` `line-length`).

---

## Type Safety

**Python**: `mypy --strict`, `warn_return_any = true`. No `Any` unless justified. Third-party libs without stubs are allowlisted per-module (`fitz`, `docling`, `cv2`, `paddleocr`, `openai`, `anthropic`, `google.genai`, `yaml`) via `ignore_missing_imports`, not a blanket project-wide ignore.

**TypeScript**: `tsc --noEmit` under `apps/web/tsconfig.json`; types for pipeline/web boundary data are generated, never hand-written (see `.ai-run/guides/architecture/architecture.md`).

---

## Per-File Ignores (justify, don't blanket-suppress)

Ruff per-file ignores are scoped to a specific rule and linked to a tracking issue, e.g. `apps/pipeline/src/atr_pipeline/stages/structure/real_block_builder.py` ignores `C901`/`PLR0912`/`PLR0915` under S5U-144 (`pyproject.toml` `[tool.ruff.lint.per-file-ignores]`). New ignores should follow the same pattern: one rule, one file, one linked issue.

---

## Quick Reference

| Need | Location |
|------|----------|
| Ruff/mypy config | `pyproject.toml` |
| oxlint config | `apps/web/.oxlintrc.json` |
| TS config | `apps/web/tsconfig.json` |
| File-length checker | `scripts/check_file_length.py` |
| Aggregate gate | `make check` |

# Code Quality Standards — apps/pipeline

**Project**: atr-pipeline | **Linter**: ruff (`pyproject.toml:35-71`)
**Formatter**: `ruff format` | **Type Checker**: mypy `--strict` (`pyproject.toml:74-89`)
**Import boundary**: `import-linter` (`pyproject.toml:91-132`)

---

## Quality Commands

| Action | Command | Description |
|--------|---------|-------------|
| Check all | `make check` | `lint && typecheck && test` — canonical local "definition of done" |
| Lint | `make lint` | ruff check + ruff format --check + mypy + lint-imports + file-length + fixture-manifest + instruction-drift + make/doc parity + codegen freshness + pnpm lint |
| Lint (pipeline only) | `uv run ruff check .` | |
| Format | `uv run ruff format .` | |
| Type check | `uv run mypy apps/pipeline/src packages/schemas/python` | mypy strict |
| Import boundaries | `uv run lint-imports` | enforces the layers contract |

**Before committing**: the 8-gate pre-commit hook runs all of the above
automatically (`.claude/hooks/pre-commit-check.sh`); `make check` is the
manual equivalent plus tests.

---

## Enforced Rules

### Ruff (`pyproject.toml:35-49`)

| Rule set | Setting | Rationale |
|----------|---------|-----------|
| `E, F, W` | error | Pyflakes/pycodestyle baseline |
| `I` | error | isort import ordering (`known-first-party = ["atr_pipeline", "atr_schemas"]`) |
| `UP` | error | pyupgrade — modern Python 3.12 syntax |
| `B` | error | bugbear — common bug patterns |
| `SIM` | error | flake8-simplify |
| `RUF` | error | ruff-native rules |
| `C901` | max-complexity 12 | McCabe cyclomatic complexity ceiling |
| `PLR0912/0913/0915` | max-branches 12, max-args 7, max-statements 50 | pylint refactor limits, tuned in `[tool.ruff.lint.pylint]` (`pyproject.toml:46-49`) |

### Per-file exceptions (`pyproject.toml:51-69`)

A hardcoded ignore is a reviewed, tracked exception — not a default:

| File | Ignored rules | Tracked by |
|------|----------------|------------|
| `stages/structure/real_block_builder.py` | `C901, PLR0912, PLR0915` | S5U-144 (config-driven structure recovery epic) |
| `stages/translation/planner.py` | `C901, PLR0912` | S5U-143 (translation planner complexity epic) |

### Formatter

| Setting | Value |
|---------|-------|
| Line length | 100 (`pyproject.toml:37`) |
| Target version | Python 3.12 |

---

## Type Safety

**Strictness**: `strict = true` (`pyproject.toml:76`), plus
`warn_return_any = true`, `warn_unused_configs = true` (`pyproject.toml:77-78`).

`ignore_missing_imports = true` is scoped to a named override list of
third-party packages without type stubs (`pyproject.toml:80-89`):
`fitz`, `docling`, `cv2`, `paddleocr`, `PIL`, `openai`, `anthropic`,
`google.genai`, `yaml`. This is a targeted carve-out, not a blanket
`ignore_missing_imports` — first-party `atr_pipeline`/`atr_schemas` code is
fully strict-checked.

### Type Rules

| Rule | Required |
|------|----------|
| Function parameters | ✅ Always (mypy strict) |
| Function returns | ✅ Always |
| `Any` | Discouraged — `.claude/rules/pipeline.md`: "no type errors, no `Any` unless justified" |
| Pydantic models for data | ✅ Required for all data models and validation (`.claude/rules/pipeline.md`) |

---

## Code Complexity Limits

| Metric | Limit | Enforced By |
|--------|-------|-------------|
| Cyclomatic complexity | 12 | ruff `C901` mccabe (`pyproject.toml:43-44`) |
| Branches per function | 12 | ruff `PLR0912` (`pyproject.toml:48`) |
| Statements per function | 50 | ruff `PLR0915` (`pyproject.toml:49`) |
| Parameters per function | 7 | ruff `PLR0913`/pylint `max-args` (`pyproject.toml:47`) |
| File length (source + test) | 400 lines | `scripts/check_file_length.py`, wired into `make lint` |

### File-length grandfather list

Pre-existing violators are tracked in `KNOWN_VIOLATORS` inside
`scripts/check_file_length.py` (e.g. `apps/pipeline/tests/unit/test_export_to_web.py`
at 919 lines, tracked by S5U-677) — a static debt ledger, not a live policy
surface. These files **must not grow further**; the gate itself is the line
count check, and the grandfather entries only suppress a hard failure on
already-oversized files.

---

## Import Organization

Enforced by ruff `I` (isort) with `known-first-party = ["atr_pipeline",
"atr_schemas"]` (`pyproject.toml:71-72`), plus the separate `import-linter`
layers contract for cross-module boundaries (see `architecture.md`).

**Rules**:
- ✅ Standard library → third-party → first-party (`atr_pipeline`/`atr_schemas`), sorted within each group.
- ❌ Wildcard imports (`import *`).
- ❌ Cross-layer imports that violate the layers contract (`atr_pipeline.stages` importing `atr_pipeline.runner.executor`, for example) — caught by `uv run lint-imports`, not ruff.

---

## Import Layer Boundaries (import-linter)

The pipeline's most distinctive quality gate: a machine-checked layered
architecture contract (`pyproject.toml:91-132`, type `"layers"`):

```
atr_pipeline.cli
  -> atr_pipeline.runner
    -> atr_pipeline.stages | atr_pipeline.eval
      -> atr_pipeline.services | atr_pipeline.store | atr_pipeline.registry
        -> atr_pipeline.config
          -> atr_pipeline.utils
```

Every cross-layer exception is named and commented individually in
`ignore_imports` (`pyproject.toml:116-131`) rather than blanket-disabled —
e.g. `atr_pipeline.stages.qa.stage -> atr_pipeline.eval.confidence_policy`
is allowed because the QA stage loads the versioned confidence-band policy,
while a hypothetical `stages -> runner.executor` import has no such
exception and fails `uv run lint-imports`.

---

## Common Violations & Fixes

| Violation | Fix |
|-----------|-----|
| `lint-imports` fails on a new cross-layer import | Either restructure to avoid the upward dependency, or add a named `ignore_imports` entry in `pyproject.toml` with a one-line rationale comment (see existing 12-entry block) |
| `check_file_length.py` fails on a new/grown file | Split the file; do not add it to `KNOWN_VIOLATORS` (that list is a closed grandfather set for pre-existing violators only) |
| `C901`/`PLR0912` complexity failure | Extract helper functions; if truly irreducible, request a per-file-ignore entry with a linked tracking issue (see `real_block_builder.py`/`planner.py` precedent) |
| mypy strict failure on a third-party import | Add the module to `[[tool.mypy.overrides]]` only if no stubs exist upstream — do not add first-party modules here |

---

## Quick Reference

| Need | Location |
|------|----------|
| Ruff config | `pyproject.toml:35-71` (repo root) |
| Mypy config | `pyproject.toml:74-89` |
| Import-linter contract | `pyproject.toml:91-132` |
| File-length gate | `scripts/check_file_length.py` |
| Aggregate local gate | `make check` (`Makefile:35`) |

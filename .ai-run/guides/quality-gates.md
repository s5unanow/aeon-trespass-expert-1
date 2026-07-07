# Quality Gates (18 total)

All work must pass **18 gates**: 9 local (pre-commit) + 9 CI (push/PR). "Passing" means CI green (all 18) — local green alone is not sufficient for merge.

## Local gates (9) — Pre-commit hook

Run automatically on `git commit` via `.claude/hooks/pre-commit-check.sh`. Target: <60 s.

### Gate 0: Secret guard

**Command:** Built into hook (no direct invocation)  
**Checks:** Blocks staged filenames (`.env`, `*.key`, `*.pem`, `credentials.json`) and content patterns (`sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers)  
**Pass signal:** Hook proceeds (no output)  
**Fail signal:** `ERROR: secret guard failed` → exits hook  
**Auto-fix:** Delete the staged file, re-stage clean files, commit  
**Skip condition:** N/A — cannot skip (hard security gate)

### Gate 1: Ruff lint

**Command:** `uv run ruff check .`  
**Checks:** Linting (includes McCabe complexity C901, max 12)  
**Pass signal:** Exit code 0; no output  
**Fail signal:** Exit code non-zero; cites violations (line:col, rule code)  
**Auto-fix:** `make format` (runs `uv run ruff check --fix .`) or manual edits  
**Skip condition:** N/A

### Gate 2: Ruff format

**Command:** `uv run ruff format --check .`  
**Checks:** Format violations (line length, spacing, import order)  
**Pass signal:** Exit code 0; no output or "X file(s) left unchanged"  
**Fail signal:** Exit code 1; cites files that would be reformatted  
**Auto-fix:** `make format`  
**Skip condition:** N/A

### Gate 3: Mypy strict typecheck

**Command:** `uv run mypy apps/pipeline/src packages/schemas/python`  
**Checks:** Type errors (no `Any` unless justified); strict mode enforced  
**Pass signal:** Exit code 0; "Success: no issues found in X file(s)"  
**Fail signal:** Exit code non-zero; cites type errors (file:line)  
**Auto-fix:** Manual (add type hints, fix logic errors)  
**Skip condition:** N/A

### Gate 4: Import layer contracts

**Command:** `uv run lint-imports`  
**Checks:** No cyclic dependencies; import layers respected  
**Pass signal:** Exit code 0  
**Fail signal:** Exit code non-zero; cites cycles or layer violations  
**Auto-fix:** Reorganize imports; break cycles  
**Skip condition:** N/A

### Gate 5: File length

**Command:** `uv run python scripts/check_file_length.py`  
**Checks:** Max 400 lines per source and test file (pre-existing violators grandfathered in `KNOWN_VIOLATORS`, must not grow)  
**Pass signal:** Exit code 0; "All files comply"  
**Fail signal:** Exit code non-zero; cites files over limit  
**Auto-fix:** Split files; refactor into modules  
**Skip condition:** Grandfathered files in `KNOWN_VIOLATORS` (no new violations allowed)

### Gate 6: Frontend lint (oxlint)

**Command:** `pnpm -r run lint` (delegates to `apps/web/.oxlintrc.json`)  
**Checks:** No import cycles; max 400 lines per component; eslint rules  
**Pass signal:** Exit code 0  
**Fail signal:** Exit code non-zero; cites violations  
**Auto-fix:** Manual (some rules allow `--fix`)  
**Skip condition:** N/A

### Gate 7: Frontend typecheck

**Command:** `pnpm -r run typecheck` (delegates to tsc in `apps/web/`)  
**Checks:** TypeScript strict mode; no type errors  
**Pass signal:** Exit code 0  
**Fail signal:** Exit code non-zero; cites type errors  
**Auto-fix:** Add type hints; fix logic  
**Skip condition:** N/A

### Gate 8: Fast test subset

**Command:** `uv run pytest -x -q --timeout=60 -m "not slow"`  
**Checks:** Unit + integration tests (excludes slow tests; fails on first error)  
**Pass signal:** Exit code 0; "X passed in Y.XXs"  
**Fail signal:** Exit code non-zero; test failure excerpt  
**Auto-fix:** Fix test assertions or production code  
**Skip condition:** Mark test with `@pytest.mark.slow` if test genuinely needs >60s  

## CI gates (9) — GitHub Actions

Run on every `push` to `main` and every PR. All 9 local gates re-run plus:

### Gate 9: Codegen freshness

**Workflow job:** `python / test`  
**Command:** `bash scripts/check_codegen_fresh.sh` (also `make check-codegen`)  
**Checks:** Generated JSON Schema + TypeScript types match Pydantic models  
**Pass signal:** Exit code 0; "Codegen is fresh"  
**Fail signal:** Exit code non-zero; cites mismatched files  
**Auto-fix:** `make codegen` (regenerates schemas locally), commit, re-push  
**Skip condition:** N/A (data contract gate)

### Gate 10: Fixture manifest validation

**Workflow job:** `python / test`  
**Command:** `uv run python scripts/validate_fixture_manifest.py` (also `make validate-fixtures`)  
**Checks:** Fixture integrity (annotation metadata, completeness)  
**Pass signal:** Exit code 0  
**Fail signal:** Exit code non-zero; cites missing/malformed fixtures  
**Auto-fix:** `make validate-fixtures` with `--bootstrap` flag (if available) or manual  
**Skip condition:** N/A

### Gate 11: Extraction scope detection

**Workflow job:** `python / test` (CI-only; needs base-branch comparison)  
**Command:** `uv run python scripts/check_extraction_scope.py`  
**Checks:** Reports when a PR touches extraction pipeline scope  
**Pass signal:** Exit code 0; "No extraction scope changes" or "Extraction scope detected — golden-refresh gate will validate"  
**Fail signal:** Exit code non-zero; cites scope violation  
**Auto-fix:** Validate golden refreshes are in separate commits (gate 12 enforces)  
**Skip condition:** N/A

### Gate 12: Golden refresh validation

**Workflow job:** `python / test` (CI-only; needs base-branch comparison)  
**Command:** `uv run python scripts/check_golden_refresh.py`  
**Checks:** When extraction scope detected, golden refreshes must be in dedicated commits with metric diffs  
**Pass signal:** Exit code 0; "Golden refreshes valid" or "No extraction scope detected"  
**Fail signal:** Exit code non-zero; cites missing/improper refreshes  
**Auto-fix:** Run extraction stage, capture golden outputs, commit separately with before/after diffs  
**Skip condition:** N/A

### Gate 13: Visual regression

**Workflow job:** `visual-regression / visual` (separate required-check context)  
**Command:** `pnpm --filter @atr/web run test:visual` (Playwright `toHaveScreenshot`)  
**Checks:** Screenshot baselines at `maxDiffPixelRatio: 0.005` (0.5% pixel diff tolerance)  
**Pass signal:** Exit code 0; "X snapshots matched"  
**Fail signal:** Exit code non-zero; cites mismatched snapshots  
**Auto-fix:** Run `pnpm --filter @atr/web run test:visual:update` locally, inspect regenerated PNGs, commit in dedicated commit (`S5U-XXX: refresh visual baselines — <reason>`), push  
**Skip condition:** N/A (baseline regen forbidden in CI — two-layer enforcement via job-local guard + content-derived scan)

### Gate 14: Visual-gate-scope scan

**Workflow job:** `visual-gate-scope / scan` (separate required-check context)  
**Command:** `python scripts/check_visual_gate_scope.py`  
**Checks:** Content-derived scan of workflow YAML + `package.json` scripts for flags that bypass visual-regression gate (`--update-snapshots`, `-u`, `--ignore-snapshots`)  
**Pass signal:** Exit code 0; "No visual-gate-scope violations"  
**Fail signal:** Exit code non-zero; cites files containing bypass flags  
**Auto-fix:** Remove the bypass flag; update the script or workflow to remove the invocation  
**Skip condition:** N/A (guards CI baseline regeneration)

### Gate 15: Coverage table scan

**Workflow job:** `coverage-table-scan / scan` (on `pull_request` only; separate required-check context)  
**Command:** Python script (requires `LINEAR_API_KEY` env var)  
**Checks:** Enforces Coverage table in PR body when Linear issue has ≥3 bullets  
**Pass signal:** Exit code 0; "Coverage table present or issue <3 bullets"  
**Fail signal:** Exit code non-zero; "Coverage table required but missing"  
**Auto-fix:** Add `## Coverage` section to PR body (see `.claude/prompts/linear-conventions.md` § "Coverage table format")  
**Skip condition:** Issue has <3 bullets (optional) OR is pure config/docs (optional by reviewer judgment)

### Gate 16: Instruction drift

**Workflow job:** `python / test`  
**Command:** `uv run python scripts/check_instruction_drift.py`  
**Checks:** Scans `*.md` for stale check-count claims, retired-term leaks, drifted safety-gate-scope enumerations; enforces CI gate count parity (CLAUDE.md header vs enumerated list vs "all K gates" claims)  
**Pass signal:** Exit code 0; "Instruction-drift check: OK"  
**Fail signal:** Exit code non-zero; cites specific drift (line:file, claim vs reality)  
**Auto-fix:** Update `CLAUDE.md` (gate counts, terminology) or rule files (`.claude/rules/`) to match code reality  
**Skip condition:** N/A (meta-gate ensuring docs stay in sync)

### Gate 17: Make-doc parity

**Workflow job:** `python / test`  
**Command:** `uv run python scripts/check_make_doc_parity.py`  
**Checks:** `make lint` target in Makefile matches CLAUDE.md command descriptions and load-bearing templates (e.g., `docs/EXTRACTION_TICKET_TEMPLATE.md`)  
**Pass signal:** Exit code 0; "Makefile/CLAUDE.md parity OK"  
**Fail signal:** Exit code non-zero; cites mismatch (command added/removed/renamed)  
**Auto-fix:** Align Makefile target with CLAUDE.md description or vice versa (both must match exactly)  
**Skip condition:** N/A (fail-closed on missing Makefile / CLAUDE.md / template per `.claude/rules/guards.md` Rule G1)

### CI full test suite

**Workflow job:** `python / test`  
**Command:** `uv run pytest --tb=short` (full suite; includes slow tests, no timeout)  
**Checks:** All unit + integration + slow tests  
**Pass signal:** Exit code 0; all tests pass  
**Fail signal:** Exit code non-zero; test failure  
**Auto-fix:** Fix failing test or production code  
**Skip condition:** Mark with `@pytest.mark.slow` (runs in CI, not in pre-commit)

## Summary table

| Gate # | Name | Scope | Command | Auto-fix | Context |
|--------|------|-------|---------|----------|---------|
| 0 | Secret guard | Local | Hook built-in | Delete file | Hard gate |
| 1 | Ruff lint | Local | `uv run ruff check .` | `make format` | Linting |
| 2 | Ruff format | Local | `uv run ruff format --check .` | `make format` | Format |
| 3 | Mypy strict | Local | `uv run mypy apps/pipeline/src packages/schemas/python` | Manual | Type check |
| 4 | Import layer | Local | `uv run lint-imports` | Manual | Imports |
| 5 | File length | Local | `uv run python scripts/check_file_length.py` | Split files | Length |
| 6 | Oxlint | Local | `pnpm -r run lint` | Manual | Frontend lint |
| 7 | Tsc | Local | `pnpm -r run typecheck` | Manual | Frontend types |
| 8 | Pytest fast | Local | `uv run pytest -x -q --timeout=60 -m "not slow"` | Fix tests | Test (fast) |
| 9 | Codegen fresh | CI | `bash scripts/check_codegen_fresh.sh` | `make codegen` | Data contract |
| 10 | Fixture manifest | CI | `uv run python scripts/validate_fixture_manifest.py` | Manual / bootstrap | Fixtures |
| 11 | Extraction scope | CI | `uv run python scripts/check_extraction_scope.py` | N/A (informational) | Extraction |
| 12 | Golden refresh | CI | `uv run python scripts/check_golden_refresh.py` | Manual (stage rerun) | Extraction |
| 13 | Visual regression | CI | `pnpm --filter @atr/web run test:visual` | `test:visual:update` | Snapshots |
| 14 | Visual-gate-scope | CI | `python scripts/check_visual_gate_scope.py` | Remove bypass flag | Visual guard |
| 15 | Coverage table | CI (PR only) | Python script + LINEAR_API_KEY | Add table to PR body | Coverage |
| 16 | Instruction drift | CI | `uv run python scripts/check_instruction_drift.py` | Update docs | Meta-gate |
| 17 | Make-doc parity | CI | `uv run python scripts/check_make_doc_parity.py` | Align Makefile / CLAUDE.md | Meta-gate |

## What "passing" means

- **Local green** (gates 0–8 pass) = safe to commit and push, but **not sufficient** for merge.
- **CI green** (all 18 gates pass) = required for merge. "Definition of Done" = CI green.

## Invoke locally before push

```bash
make check          # Runs gates 1–8 in sequence (lint + typecheck + test)
make lint           # Runs gates 1–2, 4–5, 9, 16, 17
make typecheck      # Runs gates 3, 7
make test           # Runs gate 8
make codegen        # Regenerates gates 9 input (schemas)
make check-codegen  # Validates gate 9 (codegen freshness)
```

For a final pre-push verification:

```bash
make check          # All local gates
make verify-branch-protection  # Audit live main (informational, not a gate)
git push -u origin HEAD  # Triggers CI gates on GitHub
```

# Quality Gates

18 total quality gates enforce correctness before merge. 9 run locally (pre-commit hook, ~60 s target); 9 more run in CI (required for merge).

---

## Local Gates (Pre-commit Hook)

Run automatically on every `git commit` via `.claude/hooks/pre-commit-check.sh`. All 9 must pass; hook blocks commit on failure.

### 1. Secret Guard

**Run**: Blocks staged secrets by filename (`.env`, `*.key`, `*.pem`, `credentials.json`) and content pattern (`sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers).

**Pass**: No secrets detected in staged files.
**Fail**: Commit contains secret pattern; error message lists the file and pattern. Remove the secret and re-commit.
**Auto-fix**: No. Delete the secret manually and re-stage.

---

### 2. Ruff Lint

**Run**: `uv run ruff check .`

**Pass**: All linting rules pass (includes McCabe complexity C901, max 12 per function).
**Fail**: Lint error on one or more files; error lists the file, line, and rule. Fix and re-commit.
**Auto-fix**: `uv run ruff check --fix .` (some violations can auto-fix).

---

### 3. Ruff Format

**Run**: `uv run ruff format --check .`

**Pass**: No format violations; code matches project standard.
**Fail**: Format violations on one or more files. Auto-fix and re-stage.
**Auto-fix**: `uv run ruff format .`

---

### 4. MyPy Type Check

**Run**: `uv run mypy apps/pipeline/src packages/schemas/python`

**Pass**: No type errors; all code is fully typed.
**Fail**: Type error on one or more files; error lists the file, line, and type mismatch. Fix the type or add an explicit type annotation.
**Auto-fix**: No. Must fix manually.

---

### 5. Import Linter

**Run**: `uv run lint-imports`

**Pass**: No cyclic import dependencies; import layers are clean.
**Fail**: Cyclic import or layer violation; error lists the import path. Refactor imports to break the cycle.
**Auto-fix**: No. Must refactor manually.

---

### 6. File Length

**Run**: `uv run python scripts/check_file_length.py`

**Pass**: All source and test files are ≤400 lines. Pre-existing violators are grandfathered in `KNOWN_VIOLATORS` and must not grow.
**Fail**: File exceeds 400 lines or a grandfathered violator grew. Error lists the file and line count. Split the file or refactor.
**Auto-fix**: No. Must refactor manually.

---

### 7. OXLint (Frontend)

**Run**: `pnpm -r run lint` (wraps oxlint)

**Pass**: Frontend lint passes; no `import/no-cycle` or `max-lines: 400` violations.
**Fail**: Frontend lint error; error lists the file and rule. Fix and re-commit.
**Auto-fix**: Some violations auto-fix; check the linter output.

---

### 8. TypeScript Type Check

**Run**: `pnpm -r run typecheck` → `tsc --noEmit`

**Pass**: No TypeScript errors in web code.
**Fail**: Type error; error lists the file and mismatch. Fix the type annotation.
**Auto-fix**: No. Must fix manually.

---

### 9. Pytest Fast Subset

**Run**: `uv run pytest -x -q --timeout=60 -m "not slow"` (fast tests only; pre-commit hook target)

**Pass**: All fast tests pass (marked without `@pytest.mark.slow`).
**Fail**: Test failure; error lists the test, assertion, and output. Fix the code and re-commit.
**Auto-fix**: No. Must fix the code.

**Skip if**: Tests are marked `@pytest.mark.slow` (skipped in pre-commit; CI runs full suite).

---

## CI Gates (Required for Merge)

Run on every push to `main` and every PR via GitHub Actions. All 9 must pass; branch protection blocks merge if any fail.

### 10. Codegen Fresh

**Run**: `bash scripts/check_codegen_fresh.sh`

**Pass**: Generated JSON Schema + TS types match Pydantic sources; codegen is up to date.
**Fail**: Generated files are out of sync with Pydantic models. Run `make codegen` locally and commit the diff.

---

### 11. Fixture Manifest

**Run**: `uv run python scripts/validate_fixture_manifest.py`

**Pass**: Fixture manifest is valid and all fixtures are annotated.
**Fail**: Fixture is missing annotation or manifest is malformed. Fix and commit.

---

### 12. Extraction Scope

**Run**: `uv run python scripts/check_extraction_scope.py` (needs base-branch comparison)

**Pass**: PR does not expand extraction scope without documented justification.
**Fail**: Extraction scope expanded; error lists new scope. Document justification or revert scope change.

---

### 13. Golden Refresh

**Run**: `uv run python scripts/check_golden_refresh.py` (needs base-branch comparison)

**Pass**: Golden outputs match current extraction; no stale golden state.
**Fail**: Golden outputs are stale when scope changed. Re-run extraction and commit refreshed golden state.

---

### 14. Visual Regression

**Run**: Playwright `toHaveScreenshot` test at `maxDiffPixelRatio: 0.005` (0.5% pixel tolerance)

**Pass**: Visual baselines match; no unexpected UI changes.
**Fail**: Visual diff exceeds tolerance. Update baseline locally with `pnpm --filter @atr/web run test:visual:update` and commit the PNG diff in a separate commit.

**Skip if**: PR is docs-only (marked with label).

---

### 15. Visual Gate Scope

**Run**: `python scripts/check_visual_gate_scope.py` (content-derived scan)

**Pass**: No `--update-snapshots` or `-u` flags in workflows or package.json scripts; visual baselines are never auto-regenerated in CI.
**Fail**: Forbidden flag detected. Remove the flag and re-push.

---

### 16. Coverage Table Scan

**Run**: `python scripts/coverage_table_scan.py` (on `pull_request` only)

**Pass**: PR with ≥3-bullet Linear issue has a Coverage table enumerating test scenarios.
**Fail**: Coverage table missing or malformed. Add the table per `.claude/prompts/linear-conventions.md` format and re-push.

---

### 17. Instruction Drift

**Run**: `uv run python scripts/check_instruction_drift.py`

**Pass**: CLAUDE.md check-count claims match the actual enumerated list and CI gate count. No stale rule references.
**Fail**: Drift detected (e.g., claim says "18 gates" but only 17 listed). Fix the drift in CLAUDE.md and re-push.

---

### 18. Make/Doc Parity

**Run**: `uv run python scripts/check_make_doc_parity.py`

**Pass**: `make lint` target in Makefile matches the 1-line summaries in CLAUDE.md § "Commands" and load-bearing templates.
**Fail**: Makefile and docs are out of sync. Update both and re-push.

---

## Full Gate Run

**Local aggregate** (definition of done): `make check` = `make lint && make typecheck && make test`

**CI aggregate**: all 18 gates must pass for merge. Check status with:
```bash
gh pr checks <pr-number> --watch
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Pre-commit hook blocked the commit | Run `make check` to see which gate failed; fix and re-commit |
| CI gate failed after push | Check `gh pr checks` output; fix the issue locally and push again |
| File too long (gate 6) | Refactor the file into smaller modules; cannot merge with >400-line files |
| Test failure (gate 9) | Run `uv run pytest` locally to reproduce; fix the code and commit |
| Extraction scope expanded (gate 12) | Document justification in Linear issue; if unintended, revert scope changes |
| Visual diff exceeds tolerance (gate 14) | Update baselines: `pnpm --filter @atr/web run test:visual:update`; commit PNGs in separate commit |

---

## References

- **All commands**: `Makefile` (source of truth)
- **Pre-commit hook**: `.claude/hooks/pre-commit-check.sh`
- **CI workflows**: `.github/workflows/` (gates 10–18)
- **Quality gate parity**: CLAUDE.md:35–76 (§ "Quality gates")

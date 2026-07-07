# Quality Gates

Two tiers, both must pass: **local** (pre-commit hook, fast subset, <60s target) and **CI** (full suite + extra guards). CI-green is the definition of done. The exact gate counts are drift-guarded — read `CLAUDE.md` "Quality gates" for the authoritative enumeration; this guide gives the commands.

**Canonical local aggregate**: `make check` — runs `make lint && make typecheck && make test`. Run it before pushing.

Gates below are ordered fastest-to-slowest.

### Secret guard

- **Run**: automatic in `.claude/hooks/pre-commit-check.sh` (gate 0).
- **Pass**: no staged secrets (filenames `.env`/`*.key`/`*.pem`/`credentials.json`; content `sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers).
- **Fail**: commit blocked naming the offending file/pattern. Remove the secret; never commit credentials.

### Lint (ruff + oxlint)

- **Run**: `make lint` (Python ruff check + format --check + mypy + import-linter + file-length + fixtures + instruction-drift + make/doc parity + codegen freshness + web `pnpm lint`). Web-only: `cd apps/web && pnpm lint` (oxlint).
- **Pass**: no lint errors; ruff includes McCabe complexity C901 (max 12); oxlint enforces `import/no-cycle` + `max-lines: 400`.
- **Fail**: rule id + `file:line`. **Auto-fix**: `make format` (ruff format + prettier).

### Format check

- **Run**: `uv run ruff format --check` (part of `make lint`).
- **Pass**: no formatting diffs. **Fail**: lists files. **Auto-fix**: `make format`.

### Type check (mypy + tsc)

- **Run**: `make typecheck` — mypy `--strict` (pipeline) + `tsc --noEmit` (web).
- **Pass**: zero type errors. **Fail**: `file:line: error:` per issue. No auto-fix.

### Import layer contracts

- **Run**: `uv run lint-imports` (part of `make lint`).
- **Pass**: layered contract holds (`cli > runner > stages|eval > services|store|registry > config > utils`, `pyproject.toml:91`). **Fail**: names the forbidden import; add to the reviewer-visible `ignore_imports` allowlist only if intentional.

### File length

- **Run**: `scripts/check_file_length.py` (part of `make lint`).
- **Pass**: every source/test file ≤ 400 lines (grandfathered violators must not grow). **Fail**: names the over-length file. **Fix**: split the file.

### Codegen freshness

- **Run**: `make check-codegen`.
- **Pass**: `packages/schemas/{jsonschema,ts}` match the Pydantic sources. **Fail**: drift detected. **Auto-fix**: `make codegen`, then commit the regenerated files.

### Fixture manifest

- **Run**: `make validate-fixtures` (`scripts/validate_fixture_manifest.py`).
- **Pass**: fixture manifest + annotation metadata integrity holds. **Fail**: names the mismatch.

### Tests (pytest + vitest)

- **Run**: `make test` (full: pytest + `pnpm test`). Pre-commit fast subset: `uv run pytest -x -q --timeout=60 -m "not slow"`. CI runs the full suite incl. `slow`, no timeout.
- **Pass**: all tests green. **Fail**: failing test names + assertions. **Skip if**: `slow` marker excludes long stage tests from the local fast subset only — never skip them in CI.

### Visual regression (CI)

- **Run**: `visual-regression / visual` Playwright job; local refresh via `pnpm --filter @atr/web run test:visual:update`.
- **Pass**: diff ≤ `maxDiffPixelRatio: 0.005` against committed baselines. **Fail**: page-id diff exceeds threshold. **Fix**: if the UI change is intentional, refresh baselines in a dedicated commit (`.claude/rules/visual-verify.md`). **Skip if**: never in CI — CI never regenerates baselines.

## Reporting Policy

- **Local green** = safe to commit/push, not sufficient to merge.
- **CI green** = all required checks pass = definition of done. Required blocking contexts: `python / test`, `web / test`, `visual-regression / visual`, `visual-gate-scope / scan`, `coverage-table-scan / scan`.
- If any gate fails: fix and re-run; do not merge red and do not bypass hooks without a `## Hook bypass disclosure` (`.claude/rules/hooks.md`).

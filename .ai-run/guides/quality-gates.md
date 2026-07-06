# Quality Gates

Exact commands for every gate, ordered fastest to slowest. Source of truth for the command set is the `Makefile`; the same gates run automatically on `git commit` (`.claude/hooks/pre-commit-check.sh`, 9 local checks) and in CI (18 gates total — enumerated in CLAUDE.md § Quality gates, which CI guards parse; do not renumber there casually). Local green = safe to push; CI green = definition of done.

Aggregate: `make check` (= `make lint && make typecheck && make test`) is the canonical local "definition of done".

### Format check (Python)

- **Run**: `uv run ruff format --check .`
- **Pass**: exit 0, no output (or "N files already formatted").
- **Fail**: lists files that would be reformatted — formatting drift.
- **Auto-fix**: `make format` (runs `uv run ruff format .` + `ruff check --fix` + `pnpm -r run format`).

### Lint (Python)

- **Run**: `uv run ruff check .`
- **Pass**: "All checks passed!".
- **Fail**: rule violations with file:line (includes McCabe C901 complexity > 12, PLR limits).
- **Auto-fix**: `uv run ruff check --fix .` for auto-fixable rules only.

### Lint (frontend)

- **Run**: `pnpm -r run lint` (oxlint with `import/no-cycle`, `max-lines: 400`)
- **Pass**: exit 0.
- **Fail**: oxlint diagnostics; import cycles and >400-line files are errors.

### File length

- **Run**: `uv run python scripts/check_file_length.py`
- **Pass**: silent exit 0.
- **Fail**: names files over 400 lines; pre-existing violators are grandfathered in `KNOWN_VIOLATORS` and must not grow.

### Instruction drift

- **Run**: `uv run python scripts/check_instruction_drift.py`
- **Pass**: `check_instruction_drift: OK (...)`.
- **Fail**: stale check-count claims, retired-term leaks, safety-gate-scope enumeration drift, CI gate-count disparity (Rules A–G). Fix the drifted doc, not the scanner.

### Make/doc parity

- **Run**: `uv run python scripts/check_make_doc_parity.py`
- **Pass**: silent exit 0.
- **Fail**: a `make lint` tool token in the Makefile is missing from the CLAUDE.md one-line summary or `docs/EXTRACTION_TICKET_TEMPLATE.md`. Update the doc summaries in the same PR.

### Fixture manifest

- **Run**: `uv run python scripts/validate_fixture_manifest.py`
- **Pass**: silent exit 0.
- **Fail**: fixture integrity violation — manifest and on-disk fixtures disagree.

### Type check (Python)

- **Run**: `uv run mypy apps/pipeline/src packages/schemas/python` (strict mode)
- **Pass**: "Success: no issues found".
- **Fail**: type errors; no `Any` without justification.

### Type check (frontend)

- **Run**: `pnpm -r run typecheck` (`tsc --noEmit`)
- **Pass**: exit 0, no output.
- **Fail**: TS diagnostics — commonly stale generated types; if the error is in `@atr/schemas` consumers after a model change, run `make codegen` first.

### Import contracts

- **Run**: `uv run lint-imports`
- **Pass**: "Contracts: N kept, 0 broken".
- **Fail**: a broken layer contract or import cycle — restructure the import, never edit the contract to fit.

### Codegen freshness

- **Run**: `bash scripts/check_codegen_fresh.sh` (also `make check-codegen`)
- **Pass**: silent exit 0.
- **Fail**: generated JSON Schema / TS types out of date vs Pydantic sources.
- **Auto-fix**: `make codegen`, then commit the regenerated files.

### Lint aggregate

- **Run**: `make lint`
- **Pass**: all of the above lint-family gates green in one command.
- **Fail**: first failing sub-gate's output; fix and re-run.

### Tests (fast subset — what pre-commit runs)

- **Run**: `uv run pytest -x -q --timeout=60 -m "not slow"`
- **Pass**: all tests pass within timeout.
- **Fail**: assertion/collection failures. New tests need red-before evidence (`.claude/rules/hooks.md` § "Three-input test discipline").
- **Skip if**: never skip silently; slow tests are excluded by the marker, not by hand.

### Tests (full suite)

- **Run**: `make test` (= `uv run pytest` + `pnpm -r run test`)
- **Pass**: pytest full suite (including `@pytest.mark.slow`) and vitest both green.
- **Fail**: CI runs this (`pytest --tb=short`); a local fast-subset pass is not sufficient for merge.
- **Skip if**: `codex_live`-marked tests only run when `ATR_CODEX_LIVE_SMOKE=1` is set (opt-in live smoke).

### Visual regression (CI-authoritative)

- **Run**: `pnpm --filter @atr/web run test:e2e` (Playwright, `maxDiffPixelRatio: 0.005`)
- **Pass**: screenshots match baselines in `apps/web/tests/e2e/__snapshots__/`.
- **Fail**: pixel drift beyond 0.5%. On macOS/Windows, 2–4% anti-aliasing drift is expected — the authoritative run is Linux CI.
- **Auto-fix**: for intentional UI changes only: `pnpm --filter @atr/web run test:visual:update` locally, inspect PNGs, commit in a dedicated commit. CI must never regenerate baselines (`.claude/rules/visual-verify.md`).

### Branch protection audit (after workflow changes)

- **Run**: `make verify-branch-protection`
- **Pass**: live `main` protection matches workflow-derived expected contexts.
- **Fail**: drifted required checks / `strict` / `enforce_admins` — reconcile via the append-only endpoint documented in `.claude/rules/visual-verify.md`.
- **Skip if**: no `.github/workflows/` or branch-protection change in the PR.

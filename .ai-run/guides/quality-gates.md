# Quality Gates

Sourced from `Makefile:10-20`, `pyproject.toml`, `apps/web/package.json`, and `CLAUDE.md` §"Quality gates". Ordered fastest-to-slowest, matching the local pre-commit hook sequence (`.claude/hooks/pre-commit-check.sh`).

### Secret guard

**Run**: enforced automatically inside `.claude/hooks/pre-commit-check.sh` (not a standalone `make` target)
**Pass**: no staged file matches blocked filenames (`.env`, `*.key`, `*.pem`, `credentials.json`) or blocked content (`sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers)
**Fail**: commit is blocked with the matched pattern named

### Ruff check

**Run**: `uv run ruff check .`
**Pass**: no lint violations (includes McCabe complexity C901, max 12)
**Fail**: lists violations with rule codes
**Auto-fix**: `make format` (`uv run ruff check --fix .`)

### Ruff format check

**Run**: `uv run ruff format --check .`
**Pass**: no formatting diffs
**Fail**: lists files needing reformatting
**Auto-fix**: `make format` (`uv run ruff format .`)

### Mypy strict

**Run**: `uv run mypy apps/pipeline/src packages/schemas/python`
**Pass**: no type errors under `strict = true`
**Fail**: lists type errors by file:line

### Import-linter

**Run**: `uv run lint-imports`
**Pass**: no cyclic dependencies, layer contract in `pyproject.toml:94-132` holds
**Fail**: names the violating import edge

### File length

**Run**: `uv run python scripts/check_file_length.py`
**Pass**: no source/test file exceeds 400 lines (pre-existing violators are grandfathered in a `KNOWN_VIOLATORS` list and must not grow)
**Fail**: names the offending file and line count

### oxlint (frontend)

**Run**: `pnpm -r run lint` (`apps/web`: `oxlint --import-plugin .`)
**Pass**: no `import/no-cycle` violations, no file over `max-lines: 400`
**Fail**: lists violations by file:line
**Skip if**: no frontend files changed (`.claude/skills/preflight/SKILL.md`)

### tsc --noEmit (frontend)

**Run**: `pnpm -r run typecheck` (`apps/web`: `tsc --noEmit`)
**Pass**: no type errors
**Fail**: lists type errors by file:line
**Skip if**: no frontend files changed

### Pytest (fast subset — pre-commit)

**Run**: `uv run pytest -x -q --timeout=60 -m "not slow"`
**Pass**: fast test subset green
**Fail**: first failure shown, stops at `-x`

### Pytest (full suite — CI only)

**Run**: `uv run pytest` (via `make test`, no marker filter — includes `slow`-marked tests)
**Pass**: full suite green, no timeout
**Fail**: CI run fails; branch protection blocks merge

### Codegen freshness (CI only)

**Run**: `bash scripts/check_codegen_fresh.sh` (also `make check-codegen`)
**Pass**: generated `packages/schemas/jsonschema/` and `packages/schemas/ts/` match current Pydantic sources
**Fail**: run `make codegen` and commit the regenerated output

### Fixture manifest (CI only)

**Run**: `uv run python scripts/validate_fixture_manifest.py` (also `make validate-fixtures`)
**Pass**: fixture manifest and annotation metadata are internally consistent

### Visual regression (CI only)

**Run**: Playwright `toHaveScreenshot` assertions in `apps/web/tests/e2e/*.spec.ts` against baselines in `apps/web/tests/e2e/__snapshots__/*.png`
**Pass**: `maxDiffPixelRatio: 0.005` or better on every curated page
**Fail**: pixel diff exceeds threshold — inspect the CI artifact diff, and if the change is intentional, refresh locally with `pnpm --filter @atr/web run test:visual:update` and commit the PNGs in a dedicated commit
**Skip if**: never in CI — baselines can only be regenerated locally, per `.claude/rules/visual-verify.md`

### Instruction drift / make-doc parity (CI only)

**Run**: `uv run python scripts/check_instruction_drift.py` and `uv run python scripts/check_make_doc_parity.py`
**Pass**: `*.md` files have no stale check-count claims, retired-term leaks, or `make lint`/CLAUDE.md drift
**Fail**: names the drifted claim and file

## Aggregate command

`make check` — runs `lint && typecheck && test` (the canonical local "definition of done"; does not include the CI-only gates above).

## Additional non-gating commands

`make verify` (extraction invariant checks), `make export`/`export-en` (web bundle export), `make config-health` (config drift advisory), `make erosion-report` (advisory, non-blocking), `make verify-branch-protection` (live branch-protection audit) — all present in `Makefile` but not part of the required 9 local / 18 CI gate set.

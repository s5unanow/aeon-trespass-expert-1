# Quality Gates

Transcribed from `Makefile`, `CLAUDE.md` § "Quality gates", and `.github/workflows/`. `CLAUDE.md` remains authoritative for gate count and CI enumeration (mechanically enforced by `scripts/check_instruction_drift.py` and `scripts/check_make_doc_parity.py`) — this file exists so tooling can read the same commands as data. Ordered fastest-to-slowest within each tier.

## Local (pre-commit hook, `.claude/hooks/pre-commit-check.sh`, <60s target)

### Secret guard

**Run**: (built into the hook, Gate 0) **Pass**: no `.env`/`*.key`/`*.pem`/`credentials.json` filenames and no `sk-`/`AKIA`/`ghp_`/`gho_`/PEM-header content staged **Fail**: commit blocked; remove the secret from the stage

### Ruff check

**Run**: `uv run ruff check .` **Pass**: no lint violations **Fail**: fix reported violations **Auto-fix**: `uv run ruff check --fix .`

### Ruff format check

**Run**: `uv run ruff format --check .` **Pass**: no formatting diffs **Fail**: run auto-fix **Auto-fix**: `uv run ruff format .`

### Mypy strict

**Run**: `uv run mypy apps/pipeline/src packages/schemas/python` **Pass**: no type errors **Fail**: fix the reported type error; do not add unjustified `Any`

### Import layer contracts

**Run**: `uv run lint-imports` **Pass**: no cyclic/layer-violating imports **Fail**: restructure the import to respect layer boundaries

### File length

**Run**: `uv run python scripts/check_file_length.py` **Pass**: no source/test file exceeds 400 lines (except grandfathered `KNOWN_VIOLATORS`, which must not grow) **Fail**: split the file

### Fixture manifest

**Run**: `uv run python scripts/validate_fixture_manifest.py` **Pass**: fixture manifest and annotation metadata are internally consistent **Fail**: fix the manifest or annotation drift

### Instruction drift

**Run**: `uv run python scripts/check_instruction_drift.py` **Pass**: `CLAUDE.md` check-counts, retired-term references, and safety-gate-scope enumerations agree across `.claude/skills/**`, `.claude/prompts/**` **Fail**: fix the drifted file, not the rule (see `.claude/rules/AUDIT.md` S5U-602 retrospective)

### Make/doc parity

**Run**: `uv run python scripts/check_make_doc_parity.py` **Pass**: `make lint`'s tool tokens match the one-line summary in `CLAUDE.md` and `docs/EXTRACTION_TICKET_TEMPLATE.md` **Fail**: update the drifted summary

### Codegen freshness

**Run**: `bash scripts/check_codegen_fresh.sh` **Pass**: `packages/schemas/jsonschema/**` + `packages/schemas/ts/src/generated/**` match Pydantic sources **Fail**: `make codegen`, commit the regenerated output

### pnpm lint (web)

**Run**: `pnpm -r run lint` (`oxlint --import-plugin .`) **Pass**: no lint violations, no import cycles, no file >400 lines **Fail**: fix reported violations

### tsc --noEmit (web)

**Run**: `pnpm --filter @atr/web typecheck` **Pass**: no type errors **Fail**: fix the type error — never hand-write a type for pipeline/web boundary data

### pytest fast subset

**Run**: `uv run pytest -x -q --timeout=60 -m "not slow"` **Pass**: fast subset green **Fail**: fix; re-run **Skip if**: N/A — always runs pre-commit

**Aggregate**: `make check` runs `lint && typecheck && test` (the local "definition of done").

## CI-only (GitHub Actions, in addition to all local gates)

### Extraction scope / golden refresh guard

**Run**: `scripts/check_extraction_scope.py`, `scripts/check_golden_refresh.py`, `scripts/check_threshold_changes.py` **Pass**: golden refreshes are isolated to a dedicated commit with a metric diff; threshold loosening is justified **Fail**: split the refresh into its own commit or justify the threshold change in the PR body

### Full pytest suite

**Run**: `uv run pytest --tb=short` (no `-m "not slow"` filter, no 60s timeout) **Pass**: entire suite green including `slow`-marked tests **Fail**: fix; the fast local subset is not sufficient for merge

### Coverage table scan

**Run**: `coverage-table-scan / scan` job (`.github/workflows/coverage-table-scan.yml`) **Pass**: PRs against ≥3-bullet Linear issues include the Coverage table **Fail**: add the table per `.claude/prompts/linear-conventions.md`

### Visual regression

**Run**: `visual-regression / visual` job — Playwright `toHaveScreenshot` at `maxDiffPixelRatio: 0.005` **Pass**: rendered pages match committed baselines within threshold **Fail**: either fix the unintended regression, or refresh baselines intentionally via `pnpm --filter @atr/web run test:visual:update` (`.ai-run/guides/testing/web-testing.md`)

### Visual-gate-scope scan

**Run**: `visual-gate-scope / scan` job (`scripts/check_visual_gate_scope.py`) **Pass**: no workflow/package script names `--update-snapshots`/`-u`/`--ignore-snapshots` on a CI-invoked path **Fail**: never add these flags to any CI command

### Post-merge coordinator-ack audit

**Run**: `.github/workflows/post-merge-coordinator-ack.yml` (push to `main`) **Pass**: every safety-gate-scoped merge has a coordinator-ack status on its HEAD **Fail**: not merge-blocking (audit-only); a red run is a reviewer-cross-referenced finding

---

## Quick Reference

| Need | Command |
|------|---------|
| Everything local | `make check` |
| Regenerate schemas | `make codegen` |
| Verify codegen freshness | `make check-codegen` |
| Verify fixtures | `make validate-fixtures` |
| Verify live branch protection | `make verify-branch-protection` |

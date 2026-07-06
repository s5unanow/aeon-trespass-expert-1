# Quality Gates

Ordered fastest → slowest. Prefer the `make` aggregate targets over raw tools. Local green
(`make check`) is safe-to-push; **CI green is the definition of done** — CI runs additional
gates (codegen freshness, fixture manifest, extraction scope, visual regression,
coverage-table scan). Sources: `Makefile`, `pyproject.toml`, `apps/web/package.json`,
`.claude/hooks/pre-commit-check.sh`.

### Format (auto-fix)

- **Run**: `make format` (`uv run ruff format .` + `ruff check --fix .` + `pnpm -r run format`) — `Makefile:22`
- **Pass**: files reformatted, no remaining fixable lint.
- **Auto-fix**: this *is* the fix command; run before committing.

### Lint

- **Run**: `make lint` — `Makefile:10`. Bundles: `ruff check`, `ruff format --check`,
  `mypy` (strict), `lint-imports`, `check_file_length.py`, `validate_fixture_manifest.py`,
  `check_instruction_drift.py`, `check_make_doc_parity.py`, `check_codegen_fresh.sh`, `pnpm -r run lint`.
- **Pass**: every sub-command exits 0.
- **Fail**: first failing sub-command aborts (e.g. ruff violation, mypy type error, import-layer
  breach, a source/test file > 400 lines, drifted docs, stale generated schemas).
- **Auto-fix**: `make format` for ruff; regenerate schemas with `make codegen`; other failures are manual.

### Type check

- **Run**: `make typecheck` (`uv run mypy apps/pipeline/src packages/schemas/python` + `pnpm -r run typecheck`) — `Makefile:27`
- **Pass**: `mypy --strict` and `tsc --noEmit` both clean.
- **Fail**: a type error or unjustified `Any`; means the change violates the strict contract.

### Codegen freshness

- **Run**: `make check-codegen` (`bash scripts/check_codegen_fresh.sh`) — `Makefile:52`
- **Pass**: generated `jsonschema/` + `ts/` match the Pydantic sources.
- **Fail**: you changed a model without regenerating. **Auto-fix**: `make codegen` (`Makefile:57`), then commit the regenerated files.

### Fixture manifest

- **Run**: `make validate-fixtures` (`scripts/validate_fixture_manifest.py`) — `Makefile:61`
- **Pass**: fixture manifest + annotation metadata consistent.
- **Fail**: an extraction change lacks/mismatches its fixture (`.claude/rules/extraction.md`).

### Tests

- **Run**: `make test` (`uv run pytest` + `pnpm -r run test`) — `Makefile:31`
- **Pass**: pytest + vitest green. (Pre-commit hook runs the fast subset `pytest -m "not slow"`; CI runs the full suite.)
- **Fail**: a failing test — fix the code or the test, never skip silently.
- **Skip if**: nothing — tests always run in `make check`. Slow tests are marked `@pytest.mark.slow`, not deleted.

### Full local gate (definition of done, local)

- **Run**: `make check` (= `lint` + `typecheck` + `test`) — `Makefile:35`
- **Pass**: all three aggregates green → safe to push.
- **Note**: local green is necessary but **not sufficient** — merge requires CI green.

### Visual regression (CI + optional local)

- **Run (local, intentional refresh only)**: `pnpm --filter @atr/web run test:visual:update`
- **Pass**: Playwright screenshots within `maxDiffPixelRatio: 0.005` of committed baselines.
- **Fail**: rendered output changed. If intentional, refresh baselines in a dedicated commit
  and explain in the PR (`.claude/rules/visual-verify.md`). **Never** add `--update-snapshots` to a CI command.

### Config health (advisory)

- **Run**: `make config-health` (`scripts/check_config_health.py`) — `Makefile:64`. Checks drift across
  `CLAUDE.md`/`AGENTS.md`, hooks, skills, CI. Run after entrypoint or gate-doc edits.

## Do / Don't

| ✅ DO | ❌ DON'T |
|---|---|
| Run `make check` before pushing | Push on a hunch; CI has more gates |
| `make codegen` after model changes | Hand-edit generated schemas |
| Mark slow tests, keep the fast subset fast | Delete or skip failing tests |
| Refresh visual baselines in a dedicated commit | Put `--update-snapshots` in CI |

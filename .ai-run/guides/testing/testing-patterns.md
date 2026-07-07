# Testing Patterns

Two test stacks, one monorepo. Python (pytest) for `apps/pipeline` + `packages/schemas`; TypeScript (vitest + Playwright) for `apps/web`. Exact run commands are in `quality-gates.md`; this guide covers how tests are organized and written.

## Python — pytest (`apps/pipeline`)

**Config**: root `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["apps/pipeline/tests"]` (`pyproject.toml:135`).

### Organization

Tests mirror the source package tree: `apps/pipeline/tests/{unit,integration,contract,safety_gate_corpus}/…` with subtrees like `unit/stages/`, `unit/runner/`, `unit/store/`. Shared fixtures are auto-discovered from `apps/pipeline/tests/unit/conftest.py:1`.

### Markers

| Marker | Meaning | Evidence |
|---|---|---|
| `slow` | Skipped by the pre-commit fast subset (`-m "not slow"`); runs in full CI | `pyproject.toml:137` |
| `codex_live` | Shells out to a real `codex` CLI; opt-in only via `ATR_CODEX_LIVE_SMOKE=1` | `pyproject.toml:138` |

### Red-before discipline (mandatory)

Every new `def test_…` must be verified to fail without the fix, and the PR must cite red-before evidence (a pre-fix SHA + failure excerpt, or the N/A carve-out). Full rules in `.claude/rules/hooks.md` § "Three-input test discipline".

| ✅ DO | ❌ DON'T |
|---|---|
| Confirm the test is red before the fix, then cite the SHA/excerpt | Add a test that passes with or without the fix |
| Exercise the actual code branch (happy / failure / adversarial) | Pin behavior that never reaches the new branch |

### Stage cache-hit regression tests

When a stage adds an artifact write, add a test that reaches the executor cache-hit branch and asserts the side-effect survives — the canonical example is `apps/pipeline/tests/unit/stages/translation/test_stage_cache_hit_s5u734.py`; version-bump history lives in `apps/pipeline/tests/unit/stages/qa/test_stage_version.py`. Rationale in `.claude/rules/pipeline.md` § "Stage-output cache invalidation".

## TypeScript — vitest + Playwright (`apps/web`)

### Unit / component (vitest)

- **Environment**: jsdom (`apps/web/vitest.config.ts:13`).
- **Include globs**: `tests/**/*.test.{ts,tsx}` + colocated `src/**` (`apps/web/vitest.config.ts:15`).

### End-to-end + visual regression (Playwright)

- **e2e dir**: `./tests/e2e` (`apps/web/playwright.config.ts:4`).
- **Baselines**: committed PNGs under `apps/web/tests/e2e/__snapshots__/` (`apps/web/playwright.config.ts:10`) are ground truth.
- **Threshold**: `maxDiffPixelRatio: 0.005` (`apps/web/playwright.config.ts:17`). Assertions use `toHaveScreenshot('…png')` — e.g. `apps/web/tests/e2e/extraction-regression.spec.ts:218`.

| ✅ DO | ❌ DON'T |
|---|---|
| Refresh baselines only via `pnpm --filter @atr/web run test:visual:update`, in a dedicated commit | Add `-u`/`--update-snapshots` to any CI command (blocked by `visual-gate-scope`) |
| Add a `toHaveScreenshot` + generate the baseline locally for new curated pages | Loosen the 0.005 threshold without a linked issue |

Full visual-gate stack: `.claude/rules/visual-verify.md`.

## Quick Reference

| Need | Location |
|---|---|
| pytest config + markers | `pyproject.toml:135` |
| Python fixtures | `apps/pipeline/tests/unit/conftest.py` |
| vitest config | `apps/web/vitest.config.ts` |
| Playwright config + threshold | `apps/web/playwright.config.ts` |
| Visual baselines | `apps/web/tests/e2e/__snapshots__/` |
| Test discipline rules | `.claude/rules/hooks.md`, `.claude/rules/visual-verify.md` |

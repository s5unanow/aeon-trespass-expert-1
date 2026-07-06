# Testing Patterns

Test conventions for the pipeline (pytest) and reader (vitest + Playwright). Exact run
commands are in `.ai-run/guides/quality-gates.md`.

## Frameworks

| Scope | Framework | Config |
|---|---|---|
| Pipeline unit/integration | pytest | `apps/pipeline/pyproject.toml:41` |
| Web unit | vitest | `apps/web/package.json` (`test`) |
| Web e2e / visual regression | Playwright | `apps/web/playwright.config.ts`, `apps/web/tests/e2e/` |

## Slow-test split

The pre-commit hook runs the fast subset only (`pytest -m "not slow"`); CI runs the full
suite. Mark genuinely slow tests so they don't blow the <60s local budget.

| Avoid | Prefer |
|---|---|
| A multi-second test left unmarked (slows every commit) | `@pytest.mark.slow` — marker defined `apps/pipeline/pyproject.toml:44` |
| Shelling to a real `codex` CLI in a normal test | `@pytest.mark.codex_live` + `ATR_CODEX_LIVE_SMOKE=1` opt-in (`pyproject.toml:45`) |

## Red-before discipline (mandatory)

Every PR that adds a `def test_...` (pytest) or `it(`/`test(` (vitest) must verify the test
fails without the fix and record a `Red-before confirmation:` line citing a pre-fix SHA,
failure excerpt, or the `N/A — no production code change` carve-out. A test that passes for
the wrong reason is the exact failure this guards (S5U-606, S5U-604). Full contract:
`.claude/rules/hooks.md` § "Three-input test discipline".

## Three-input rule for gating logic

Any new decision/pattern-match that gates on a condition needs three documented inputs:
happy-path (passes), failure (blocks), and an adversarial/mixed edge. Applies to hook
scripts and prompt/skill gating logic (`.claude/rules/hooks.md`).

## Visual regression

Baselines at `apps/web/tests/e2e/__snapshots__/*.png` are ground truth, diffed at
`maxDiffPixelRatio: 0.005`. CI never regenerates them; refresh intentionally with
`pnpm --filter @atr/web run test:visual:update` in a dedicated commit and explain the delta
in the PR. macOS dev machines drift 2–4% vs the Linux CI runner — CI is authoritative
(`.claude/rules/visual-verify.md`). Adding a curated page = a new `toHaveScreenshot(...)`
assertion + committed baseline PNG.

## Fixtures (extraction)

Fixtures are mandatory for every extraction change and validated by
`validate_fixture_manifest.py` (`make validate-fixtures`). Golden refreshes go in separate
commits with before/after metric diffs (`.claude/rules/extraction.md`).

## Do / Don't

| ✅ DO | ❌ DON'T |
|---|---|
| Cite red-before evidence for each new test | Add a test with no proof it was ever red |
| Mark slow tests `@pytest.mark.slow` | Leave slow tests in the pre-commit fast subset |
| Refresh visual baselines in a dedicated commit | Add `--update-snapshots` to any CI command |
| Add a fixture for every extraction change | Change extraction output without a fixture |

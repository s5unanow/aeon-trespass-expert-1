# Web Testing (apps/web)

**Unit/component framework**: Vitest (`apps/web/package.json:13-14`) | **E2E/visual**: Playwright (`apps/web/package.json:15-16`)
**Test location**: `apps/web/tests/` (Playwright specs + snapshots), colocated `*.test.tsx` for Vitest

---

## Running Tests

| Action | Command |
|--------|---------|
| Unit/component tests | `pnpm --filter @atr/web test` (`vitest run`) |
| Watch mode | `pnpm --filter @atr/web test:watch` |
| E2E (Playwright) | `pnpm --filter @atr/web test:e2e` |
| Type check | `pnpm --filter @atr/web typecheck` (`tsc --noEmit`) |
| Lint | `pnpm --filter @atr/web lint` (`oxlint --import-plugin .`) |

---

## Visual Regression

Baselines live at `apps/web/tests/e2e/__snapshots__/*.png`, diffed at `maxDiffPixelRatio: 0.005` (`apps/web/playwright.config.ts`). To intentionally update a baseline after a legitimate UI change:

```bash
pnpm --filter @atr/web run test:visual:update
```

**Never** add `-u` / `--update-snapshots` / `--ignore-snapshots` to any CI-invoked command — two independent guards block this (`scripts/check_test_e2e_flags.sh`, `scripts/check_visual_gate_scope.py`). Full gate stack: `.claude/rules/visual-verify.md`.

**Platform note**: baselines are captured on Linux CI. macOS/Windows runs typically show 2-4% drift from anti-aliasing even with no code change — CI is the authoritative run.

---

## Manual Visual Verification (before a PR touching rendering)

For changes to `apps/web/src/components/**`, `apps/web/src/routes/**`, `apps/web/src/styles/**`, or pipeline render/export stages:

1. Ensure the dev server is running on `localhost:3001`.
2. Navigate via Playwright MCP to `http://localhost:3001/documents/ato_core_v1_1/{edition}/{pageId}`.
3. Screenshot (fullPage) and visually confirm.

Full steps: `.claude/rules/visual-verify.md`.

---

## Component Test Pattern

Route components fetch data in a `useEffect` guarded against stale responses with `AbortController` (`apps/web/src/routes/ReaderPage.tsx:14-27`). Test these by asserting on the rendered output after the resolved promise, not by asserting on intermediate loading state timing.

---

## Quick Reference

| Need | Location |
|------|----------|
| Vitest config | `apps/web/vitest.config.ts` |
| Playwright config | `apps/web/playwright.config.ts` |
| E2E specs + baselines | `apps/web/tests/e2e/` |
| Lint config | `apps/web/.oxlintrc.json` |
| Visual-regression full rule | `.claude/rules/visual-verify.md` |

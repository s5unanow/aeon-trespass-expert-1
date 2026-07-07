# Testing Patterns — @atr/web

**Framework**: vitest 3 (unit/component, jsdom) + Playwright 1.50 (e2e + visual regression)
**Test location**: `apps/web/tests/{unit,component,e2e}`

## Test Organization

```
tests/
├── unit/          Node-level tests (e.g. codegen helper: generateTsTypes.test.ts)
├── component/     React components + lib functions via @testing-library/react
└── e2e/           Playwright specs against the built preview server
    └── __snapshots__/   committed visual-regression PNG baselines
```

Naming: `<Subject>.test.tsx` for components, `<function>.test.ts` for lib code, `<area>.spec.ts` for Playwright (`tests/e2e/extraction-regression.spec.ts`, `tests/e2e/reader-page.spec.ts`).

## Running Tests

| Action | Command (from apps/web, or `pnpm --filter @atr/web run …`) |
|---|---|
| Unit + component | `pnpm test` (`vitest run`) |
| Watch mode | `pnpm test:watch` |
| e2e + visual | `pnpm test:e2e` (`playwright test`) |
| Refresh visual baselines (LOCAL ONLY) | `pnpm test:visual:update` |

Vitest config: jsdom environment, includes `tests/**/*.test.{ts,tsx}` and `src/**/*.test.{ts,tsx}` (`vitest.config.ts:13-16`). Playwright builds and serves the production bundle on port 4173 before running (`playwright.config.ts:29-33`), so e2e exercises the real exported `public/documents` fixtures.

## Component Test Pattern

Render through `@testing-library/react`; components that call router hooks must be wrapped in `MemoryRouter` — the suite defines a local `renderWithRouter` helper (`tests/component/BlockRenderer.test.tsx:12-14`).

```tsx
// tests/component/BlockRenderer.test.tsx:25-27
renderWithRouter(<BlockRenderer block={block} />);
expect(screen.getByText('Проверка атаки')).toBeDefined();
```

Test data is built inline as typed literals (`const block: RenderBlock = {...}`) — the reader-local types from `src/lib/render/types.ts` keep fixtures honest; there is no factory layer.

## Mocking

| What | How | Source |
|---|---|---|
| Network (`fetch`) | `vi.spyOn(globalThis, 'fetch')` + `mockResolvedValue(Once)` per response; `mockReset` in `afterEach` | `tests/component/loadRenderPage.test.ts:5-9` |
| 404-fallback chains | Sequenced `mockResolvedValueOnce` calls, then assert both URLs were fetched | `tests/component/loadRenderPage.test.ts:29-43` |

Loader tests assert error messages including status + URL (`tests/component/loadRenderPage.test.ts:45-59`) and that the normalizer materialized defaults (`:16-23`). No module mocks (`vi.mock`) are in use — the fetch boundary is the only seam.

## E2E Pattern

Curated fixture pages under `public/documents/` are enumerated as data-driven specs (`tests/e2e/extraction-regression.spec.ts:55-92`) asserting DOM structure per block kind, icon counts, and source-page badges.

Console errors fail tests. The collector allowlists only the best-effort `manifest.json` 404 — matched on `msg.location().url`, never on generic error text, so any other 404 still fails (`tests/e2e/extraction-regression.spec.ts:22-36`, S5U-1234).

## Visual Regression

Authoritative policy: `.claude/rules/visual-verify.md` § "Visual regression CI gate (S5U-599)" — read it before touching anything here. Summary of the local mechanics:

- Baselines are committed PNGs at `tests/e2e/__snapshots__/*.png` (path set by `snapshotPathTemplate`, `playwright.config.ts:10`).
- Threshold: `toHaveScreenshot: { maxDiffPixelRatio: 0.005 }`, configured centrally (`playwright.config.ts:17`). Do not loosen or add per-test overrides without a linked issue.
- Intentional UI change: run `pnpm --filter @atr/web run test:visual:update` locally, inspect the PNGs, commit them in a dedicated commit. **CI never regenerates baselines** — enforcement layers are described in the rule file.
- Stabilize snapshots by hiding elements that overlay the captured region, e.g. the floating feedback button (`tests/e2e/extraction-regression.spec.ts:214-218`).
- Baselines are captured on Linux CI; macOS runs typically drift 2–4% from font hinting alone — expected, CI is authoritative (see the rule file's platform note).

Adding a curated page: add a `toHaveScreenshot('name.png')` assertion in a spec (`tests/e2e/extraction-regression.spec.ts:297-303` is the canonical shape), generate the baseline locally, commit spec + PNG together.

## Writing New Tests

| Rule | Detail |
|---|---|
| Red-before evidence is mandatory for every new test function | See `.claude/rules/hooks.md` § "Three-input test discipline" (authoritative) — cite a pre-fix SHA or failure excerpt in the commit/PR |
| Component touching router hooks | Wrap in `MemoryRouter` (`tests/component/BlockRenderer.test.tsx:9-14`) |
| New loader | Spy on `fetch`; cover happy path, 404 fallback, and non-404 hard failure (`tests/component/loadRenderPage.test.ts`) |
| Rendering-affecting change | Verify visually before PR per `.claude/rules/visual-verify.md` (Playwright MCP flow) |

## Quick Reference

| Need | Location |
|---|---|
| Vitest config | `apps/web/vitest.config.ts` |
| Playwright config (threshold, webServer) | `apps/web/playwright.config.ts` |
| Visual baselines | `apps/web/tests/e2e/__snapshots__/` |
| E2E fixture bundles | `apps/web/public/documents/` |
| Visual-gate policy | `.claude/rules/visual-verify.md` |

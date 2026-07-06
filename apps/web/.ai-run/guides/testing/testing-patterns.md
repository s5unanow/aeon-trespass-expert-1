# Testing Patterns — apps/web

**Project**: `@atr/web`
**Frameworks**: Vitest 3 (unit/component, `apps/web/package.json:39`) + Playwright 1.50
(e2e + visual regression, `apps/web/package.json:27`)
**Test Locations**: `apps/web/tests/component/`, `apps/web/tests/unit/`, `apps/web/tests/e2e/`

Two distinct test layers exist and are not interchangeable:

- **Vitest** (jsdom) for component rendering and pure-function/module unit tests — fast,
  no browser, mocks `fetch`.
- **Playwright** (real Chromium via a built+previewed app) for DOM-integration checks and
  pixel-level visual regression against committed baseline PNGs.

---

## Test Organization

```
apps/web/tests/
├── component/     Vitest + @testing-library/react: component rendering, lib/api unit tests
│                  (*.test.tsx for components, *.test.ts for lib modules)
├── unit/          Vitest: codegen script unit tests (generateTsTypes.test.ts)
└── e2e/
    ├── reader-page.spec.ts             Playwright: walking-skeleton smoke test
    ├── extraction-regression.spec.ts   Playwright: curated-page DOM + visual regression
    └── __snapshots__/*.png             Committed visual-regression baselines
```

### Naming Conventions

| Element | Pattern | Example |
|---------|---------|---------|
| Vitest test files | `<Subject>.test.ts(x)` | `apps/web/tests/component/BlockRenderer.test.tsx` |
| Playwright spec files | `<area>.spec.ts` | `apps/web/tests/e2e/extraction-regression.spec.ts` |
| Visual baselines | `<page-id>.png` under `__snapshots__/` | `apps/web/tests/e2e/__snapshots__/icon-dense-en-p0001.png` |

---

## Running Tests

| Action | Command |
|--------|---------|
| All Vitest tests | `pnpm test` (`vitest run` — `apps/web/package.json:13`) |
| Watch mode | `pnpm test:watch` (`vitest` — `apps/web/package.json:14`) |
| All Playwright e2e/visual | `pnpm test:e2e` (`playwright test` — `apps/web/package.json:15`) |
| Refresh visual baselines (LOCAL ONLY) | `pnpm test:visual:update` (`playwright test --update-snapshots` — `apps/web/package.json:16`) |
| Single Vitest file | `pnpm exec vitest run tests/component/BlockRenderer.test.tsx` |
| Single Playwright spec | `pnpm exec playwright test tests/e2e/reader-page.spec.ts` |

---

## Unit / Component Test Pattern

```tsx
// Source: apps/web/tests/component/BlockRenderer.test.tsx:12-14,17-27
function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}
// ... renderWithRouter(<BlockRenderer block={block} />); expect(screen.getByText(...))
```

Components that use router hooks (e.g. `GlossaryText` inside `InlineRenderer` calls
`useNavigate`) must be wrapped in `MemoryRouter` — `apps/web/tests/component/BlockRenderer.test.tsx:9-14`.
Assertions favor `screen.getByText`/`getByRole` and direct DOM inspection
(`container.querySelector`, `.dataset.variant`) over snapshot matching —
`apps/web/tests/component/BlockRenderer.test.tsx:83-88`.

---

## Mocking

Network I/O is mocked at the `fetch` boundary with `vi.spyOn`, not with a request-library
mock — `lib/api/*.ts` all call the global `fetch` directly.

```ts
// Source: apps/web/tests/component/loadRenderPage.test.ts:5,7-9,13
const fetchSpy = vi.spyOn(globalThis, 'fetch');
afterEach(() => { fetchSpy.mockReset(); });
fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);
```

| What | How | Source |
|------|-----|--------|
| Bundle fetch (edition fallback, 404, network error) | `vi.spyOn(globalThis, 'fetch')` with `mockResolvedValueOnce` chains | `apps/web/tests/component/loadRenderPage.test.ts:29-43` (fallback), `:139-143` (network failure) |
| Router context for components using `useNavigate`/`useParams` | Wrap render in `<MemoryRouter>` | `apps/web/tests/component/BlockRenderer.test.tsx:12-14` |

---

## Async Testing

All fetch-boundary tests are `async`/`await` against promises returned by `lib/api/*`
functions; `AbortSignal` propagation is asserted explicitly rather than mocked away.

```ts
// Source: apps/web/tests/component/loadRenderPage.test.ts:145-154
const controller = new AbortController();
await loadRenderPage('doc1', 'p0001', 'ru', controller.signal);
expect(fetchSpy).toHaveBeenCalledWith(/* ... */, { signal: controller.signal });
```

---

## Content-Derived Parameterized Tests

Rather than `@pytest`-style table decorators, Playwright specs build a spec array and loop
over it with `test.describe`/`test`, so adding a new curated page is a one-entry data change:

```ts
// Source: apps/web/tests/e2e/extraction-regression.spec.ts:55-92,108-109
const CURATED_PAGES: PageSpec[] = [ /* documentId, pageId, blockCount, blockKinds, ... */ ];
for (const spec of CURATED_PAGES) {
  test.describe(`EN extraction: ${spec.documentId}/${spec.pageId}`, () => { /* ... */ });
}
```

The same content-derived-over-hardcoded principle drives the codegen unit test, which walks
every committed JSON Schema file rather than a maintained list of names:

```ts
// Source: apps/web/tests/unit/generateTsTypes.test.ts:21-24,27-30
async function schemaStems(): Promise<string[]> {
  const files = (await readdir(SCHEMA_DIR)).filter((f) => f.endsWith('.schema.json'));
  return files.map((f) => basename(f, '.schema.json')).sort();
}
```

That test also pins a fail-loud invariant: `derivePrimaryType` must throw (naming the schema
stem) rather than silently skip a schema with no `title` —
`apps/web/tests/unit/generateTsTypes.test.ts:61-67`.

---

## Visual Regression Testing (Playwright)

Baselines are committed PNGs diffed at a fixed pixel-ratio tolerance on every PR; this is a
**mechanically enforced** repo-wide gate, not an optional convention — see
`.claude/rules/visual-verify.md` § "Visual regression CI gate (S5U-599)" for the full
enforcement stack.

| Setting | Value | Source |
|---------|-------|--------|
| Baseline location | `{testDir}/{testFileDir}/__snapshots__/{arg}{ext}` -> `apps/web/tests/e2e/__snapshots__/*.png` | `apps/web/playwright.config.ts:10` |
| Pixel tolerance | `maxDiffPixelRatio: 0.005` (0.5%) | `apps/web/playwright.config.ts:11-17` |
| Preview server | `pnpm run build && pnpm run preview` on port 4173 | `apps/web/playwright.config.ts:29-33` |

```ts
// Source: apps/web/tests/e2e/extraction-regression.spec.ts:209-219
await expect(content.locator('.reader-callout')).toBeVisible();
await page.waitForLoadState('networkidle');
await expect(content).toHaveScreenshot('table-callout-en.png');
```

**Never pass `--update-snapshots`/`-u` in CI.** `test:visual:update`
(`apps/web/package.json:16`) is local-only — regenerate baselines on your own machine,
inspect the PNG diff, and commit it in a dedicated commit. CI enforces this with a two-layer
guard (a job-local flag scan plus a separate content-derived workflow scanner); see
`.claude/rules/visual-verify.md` for the full mechanism. Baselines are captured on Linux CI —
local runs on macOS/Windows will show 2-4% drift from anti-aliasing even with no code change,
which is expected and non-blocking locally (CI is authoritative).

---

## Test Environment

Vitest runs component/unit tests under `jsdom` with no global setup files:

```ts
// Source: apps/web/vitest.config.ts:12-16
test: {
  environment: 'jsdom',
  setupFiles: [],
  include: ['tests/**/*.test.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
},
```

---

## Common Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `afterEach(() => fetchSpy.mockReset())` | Reset the shared fetch spy between cases in a `describe` block | `apps/web/tests/component/loadRenderPage.test.ts:7-9` |
| `test.beforeEach` console-error collector | Fail a Playwright test on any unexpected console error, with an explicit URL-based allowlist (not a text-substring filter) | `apps/web/tests/e2e/extraction-regression.spec.ts:22-25,112-114` |

---

## Quick Reference

| Need | Location |
|------|----------|
| Vitest config | `apps/web/vitest.config.ts` |
| Playwright config | `apps/web/playwright.config.ts` |
| Visual baselines | `apps/web/tests/e2e/__snapshots__/` |
| Component tests | `apps/web/tests/component/` |
| e2e/visual specs | `apps/web/tests/e2e/` |

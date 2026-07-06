# Testing Patterns

**Project**: `@atr/web` (apps/web)
**Frameworks**: vitest 3 (jsdom + @testing-library/react) for unit/component; Playwright for e2e + visual regression
**Test location**: `tests/` (`unit/`, `component/`, `e2e/`)

Authoritative repo rules: `.claude/rules/visual-verify.md` (visual gate),
`.claude/rules/hooks.md` (red-before discipline). This guide summarizes them;
the rules files win on any conflict.

## Test Organization

```
tests/
├── unit/                  Node-level tests (e.g. codegen helper: tests/unit/generateTsTypes.test.ts:16)
├── component/             jsdom tests for components, contexts, and lib/api loaders
└── e2e/                   Playwright specs against the built preview server
    └── __snapshots__/     Committed visual-regression PNG baselines (ground truth)
```

Vitest picks up `tests/**/*.test.{ts,tsx}` and `src/**/*.test.{ts,tsx}` in a jsdom
environment (`vitest.config.ts:13-15`). Playwright is scoped to `tests/e2e`
(`playwright.config.ts:4`).

### Naming Conventions

| Element | Pattern | Example |
|---|---|---|
| Component/lib tests | `<Subject>.test.tsx` / `<subject>.test.ts` | `tests/component/BlockRenderer.test.tsx` |
| E2E specs | `<area>.spec.ts` | `tests/e2e/extraction-regression.spec.ts` |
| Visual baselines | `<page-id>.png` under `__snapshots__/` | `tests/e2e/__snapshots__/icon-dense-en-p0001.png` |

## Running Tests

Scripts from `package.json:13-16`; run via `pnpm --filter @atr/web run <script>`
(or `pnpm run <script>` inside `apps/web`).

| Action | Command |
|---|---|
| Unit + component (CI mode) | `pnpm --filter @atr/web run test` (`vitest run`) |
| Watch mode | `pnpm --filter @atr/web run test:watch` |
| Single file | `pnpm --filter @atr/web exec vitest run tests/component/TableBlock.test.tsx` |
| E2E + visual | `pnpm --filter @atr/web run test:e2e` (`playwright test`) |
| Update visual baselines (LOCAL ONLY) | `pnpm --filter @atr/web run test:visual:update` (`package.json:16`) |

No coverage tool is configured for this package; the quality gates are the test
suites themselves plus lint/typecheck.

## Component Test Pattern

Canonical shape — `tests/component/BlockRenderer.test.tsx:12-14`: components that
use router hooks (e.g. `GlossaryText` → `useNavigate`) must render inside a
`MemoryRouter`:

```tsx
function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}
```

Build props as reader-projection types (`RenderBlock` from `src/lib/render/types.ts`),
render, assert with `screen.getByText` / jest-dom matchers.

## Mocking

The reader's only IO is `fetch` against static JSON — mock it, nothing else.

| What | How | Source |
|---|---|---|
| `fetch` (all `lib/api` loaders) | `vi.spyOn(globalThis, 'fetch')` + `mockResolvedValue({ ok: true, json: … } as Response)` | `tests/component/loadRenderPage.test.ts:5` |
| Edition→root fallback path | `mockResolvedValueOnce` 404 then success | `tests/component/loadRenderPage.test.ts:29-43` |

Reset spies in `afterEach` (`tests/component/loadRenderPage.test.ts:7-9`). Loader tests
must cover the failure branches too — non-404 errors, invalid `schema_version`, unknown
block/inline kinds (`tests/component/loadRenderPage.test.ts:80-137`).

## E2E Testing (Playwright)

- The web server is built + served automatically: `pnpm run build && pnpm run preview`
  on port 4173 (`playwright.config.ts:29-33`); tests navigate to
  `/documents/<docId>/<edition>/<pageId>` fixture bundles committed under `public/documents/`.
- Smoke pattern: `tests/e2e/reader-page.spec.ts:3` (walking-skeleton page renders, icons
  have alt text, source badge visible).
- Curated-page regression: data-driven loop over `CURATED_PAGES` specs
  (`tests/e2e/extraction-regression.spec.ts:55`) asserting block counts, kinds, icons.
- Console errors fail tests. Only the best-effort `manifest.json` 404 is allowlisted, and
  by resource URL — not by generic error text (`tests/e2e/extraction-regression.spec.ts:22-25`).

## Visual Regression Gate

Full stack: `.claude/rules/visual-verify.md` § "Visual regression CI gate (S5U-599)".
The essentials:

| Rule | Detail |
|---|---|
| Baselines are ground truth | `tests/e2e/__snapshots__/*.png`, committed to git; path template at `playwright.config.ts:10` |
| Threshold | `toHaveScreenshot: { maxDiffPixelRatio: 0.005 }` (`playwright.config.ts:17`) — do NOT loosen without a linked issue |
| Intentional UI change | Run `pnpm --filter @atr/web run test:visual:update` locally, inspect PNGs, commit in a dedicated commit with the reason |
| CI never regenerates baselines | Never add `-u` / `--update-snapshots` / `--ignore-snapshots` to any CI command — enforced by `scripts/check_test_e2e_flags.sh` and the `visual-gate-scope / scan` job |
| Linux CI is authoritative | macOS/Windows produce 2–4% font/AA drift that exceeds 0.005; if a local refresh fails on CI, commit the PNGs from the CI test-results artifact instead |

Snapshot assertions live in the e2e specs, e.g.
`tests/e2e/extraction-regression.spec.ts:218` (`table-callout-en.png`) and `:302`
(`icon-dense-en-p0001.png`). To add a curated page: add a `toHaveScreenshot('<id>.png')`
assertion, generate the baseline locally, commit spec + PNG together. Hide the floating
feedback button before short-page snapshots (`tests/e2e/extraction-regression.spec.ts:216`).

## Red-Before Discipline (new tests)

Every PR adding a new `it(` / `test(` (vitest) or Playwright test must verify the test
fails without the fix and cite evidence — a `Red-before confirmation:` line in the commit
message or PR body with a pre-fix SHA or failure excerpt, or the literal
"N/A — no production code change" carve-out. Authoritative form, SHA-resolution tripwire,
and parametrize (`test.each`) carve-outs: `.claude/rules/hooks.md` § "Three-input test
discipline". Reviewers mechanically resolve cited SHAs; fabricated or unreachable SHAs
grade CRITICAL.

## Writing New Tests

1. Component/lib: `tests/component/<Subject>.test.tsx`; wrap in `MemoryRouter` if any
   child touches router hooks; mock `fetch` if the subject loads data.
2. Use reader-projection types from `src/lib/render/types.ts` for fixture data so schema
   drift breaks the test at compile time.
3. E2E: add fixture bundle under `public/documents/<docId>/` if needed, then a spec in
   `tests/e2e/`.
4. Run the fast loop: `pnpm --filter @atr/web run test`, then `test:e2e` before PR.
5. Record red-before evidence (see above).

## Quick Reference

| Need | Location |
|---|---|
| Vitest config (jsdom, globs) | `vitest.config.ts` |
| Playwright config (threshold, webServer) | `playwright.config.ts` |
| Visual baselines | `tests/e2e/__snapshots__/` |
| E2E fixture bundles | `public/documents/` |
| Visual gate rules (authoritative) | `.claude/rules/visual-verify.md` |
| Red-before rules (authoritative) | `.claude/rules/hooks.md` |

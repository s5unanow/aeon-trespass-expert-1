# 005 — Reader navigation: stop re-fetching the glossary and QA bundle on every page turn; fix the hash-bounce history bug; client-route the index page

- **Priority:** P1 — user-facing performance + two navigation-correctness bugs on the app's hottest path
- **Effort:** M
- **Fix risk:** LOW
- **Dependency:** none
- **Category:** web performance / correctness
- **Planned-at commit:** `fc98b82`
- **Safety-gate scope:** NO. But all files are under `apps/web/src/{components,routes}/**`, which is on the **visual-verify** path list (`.claude/rules/visual-verify.md`) — visual verification before PR is mandatory, and the CI `visual-regression / visual` gate diffs against committed baselines (`apps/web/tests/e2e/__snapshots__/*.png`, threshold 0.005).

## Why this matters

Page navigation is the core interaction of the reader. Verified at fc98b82, every single page turn:

1. **Re-fetches glossary.json (213 KB for `ato_core_v1_1/ru`) and rebuilds both lookup Maps.** `ReaderPage` resets `page` to `null` on every `pageId` change, which makes the component return the loading skeleton — *unmounting* `GlossaryProvider` (it sits below the early return). On remount the provider's effect re-runs `loadGlossary` (a bare uncached `fetch`). Besides the network/CPU churn, glossary keyword links and icon tooltips visibly pop in late on every page ("flash of unlinked text").
2. **Re-downloads the whole document's QA bundle twice** (`qa_summary.json` + `qa_records.json`, ~60 KB+) — `QaPageBadge`'s effect lists `pageId` in its deps but the fetched bundle is per-document/edition; only the derived count is per-page.
3. **Pushes spurious history entries on anchor deep links.** `ReaderPage`'s hash effect re-bounces `window.location.hash` (`''` then `hash`) to force `:target` re-evaluation. Each assignment pushes a history entry, so Back lands on `…#` then `…#hash` instead of leaving the page. This exact bug class was already fixed in `GlossaryPage` (S5U-584) by replacing `:target` with a highlight class — the comment there documents the rationale. `QaDashboard` links into reader anchors (`pageId#entity_ref`), so this is a live path.
4. **The index page's page pills are raw `<a href>`** — every entry into a document tears down the SPA and re-downloads the bundle, while every other component correctly uses react-router `Link`. Bonus defect: the index conflates fetch failure with "No documents found" (catch only does `setLoading(false)`).

## Current state (verified at fc98b82)

`apps/web/src/routes/ReaderPage.tsx:24-41` — `setPage(null)` on every param change; `:67-79` — `if (!page)` returns the skeleton; `:82` — `<GlossaryProvider documentId={documentId!} edition={edition!}>` below that return (so it unmounts during every load).

`apps/web/src/routes/ReaderPage.tsx:51-62` — the hash effect:
```tsx
    el.scrollIntoView({ block: 'start' });
    if (!el.matches(':target')) {
      window.location.hash = '';
      window.location.hash = hash;
    }
```

`apps/web/src/contexts/GlossaryContext.tsx` (provider) — effect keyed `[documentId, edition]`, calls `loadGlossary`, builds `byIcon`/`byConcept` Maps in a `useMemo`.

`apps/web/src/lib/api/loadGlossary.ts` — plain `fetch`, no cache:
```ts
export async function loadGlossary(documentId: string, edition: string = 'ru'): Promise<GlossaryPayloadV1> {
  const url = `/documents/${documentId}/${edition}/data/glossary.json`;
  const res = await fetch(url);
```

`apps/web/src/components/nav/QaPageBadge.tsx:21-37` — `loadQa(documentId, edition, signal)` inside an effect with deps `[documentId, edition, pageId]`.

`apps/web/src/routes/DocumentIndexPage.tsx:70` — `.catch(() => setLoading(false));`; `:86-87` — `manifests.length === 0 ? <p className="index-empty">No documents found</p>`; `:104-110` — `<a key={p.page_id} href={...} className="page-pill">`.

`apps/web/src/routes/GlossaryPage.tsx:38-45` — the S5U-584 precedent comment ("…that bounce inserted spurious history entries and broke browser-back").

Where the layout lives: `ReaderPage` renders inside `ReaderLayout` (route parent) which already holds `documentId`/`edition` params — the natural new home for `GlossaryProvider`.

Existing tests: `apps/web/tests/component/ReaderPage.test.tsx` (6 tests, nothing on the hash effect), `GlossaryContext.test.tsx`, `ReaderLayout.test.tsx` (13 cases), `DocumentIndexPage.test.tsx`, `loadQa.test.ts`. **No tests exist for `QaPageBadge`.** E2E: `apps/web/tests/e2e/reader-page.spec.ts`, `extraction-regression.spec.ts`.

## Repo conventions that bind this change

- `.claude/rules/web.md`: no manual TS types (use `@atr/schemas`); oxlint `import/no-cycle`, `max-lines: 400`; `tsc --noEmit`.
- `.claude/rules/visual-verify.md`: dev server on `localhost:3001`, Playwright MCP navigate + screenshot affected pages, verify interactivity. If rendered output of curated baseline pages legitimately changes, refresh baselines via `pnpm --filter @atr/web run test:visual:update` in a **dedicated commit** with per-PNG explanation in the PR body (none of these fixes should change static rendering, so baseline churn is a red flag — see STOP conditions).
- Vitest tests need `Red-before confirmation:` evidence (applies to `it(`/`test(` additions).
- Coverage table required if the Linear issue has ≥3 bullets — this plan has 4 sub-fixes; write the issue with explicit bullets and mirror them in the table.

## Scope

**In scope:**
- `apps/web/src/routes/ReaderPage.tsx` (hash effect; remove provider if lifted)
- `apps/web/src/routes/ReaderLayout.tsx` (new `GlossaryProvider` home)
- `apps/web/src/lib/api/loadGlossary.ts` (module-level promise cache)
- `apps/web/src/lib/api/loadQa.ts` (module-level promise cache)
- `apps/web/src/components/nav/QaPageBadge.tsx` (dep split / cached bundle)
- `apps/web/src/routes/DocumentIndexPage.tsx` (`Link`, error state)
- `apps/web/src/styles/**` (highlight class for the `:target` replacement, mirroring the glossary's `glossary-card-highlight`)
- Tests under `apps/web/tests/component/` and, if feasible, one e2e navigation journey

**Explicitly out of scope:**
- `loadRenderPage` per-page caching/prefetching (different tradeoff — pages are many; design separately)
- `QaDashboard` internals (it benefits automatically from the `loadQa` cache)
- Service-worker/HTTP-cache headers, bundle-splitting, anything in `packages/schemas/` or the pipeline
- The e2e console-error filter fix (`extraction-regression.spec.ts:21-23`) — separate quick-win issue

## Git workflow

1. File a Linear issue (ATE1/S5U) with one bullet per sub-fix; mark In Progress.
2. `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-reader-navigation-caching`
3. Commits prefixed `S5U-XXX:`; one commit per sub-fix keeps review tractable. **Do not push or open a PR unless the user instructs.**

## Ordered steps

### Step 1 — Promise caches in the loaders (red tests first)

Add tests in `apps/web/tests/component/` (or alongside `loadQa.test.ts`): calling `loadGlossary(doc, ed)` twice yields one `fetch` call (mock `fetch`, assert call count 1, same resolved object); different `(doc, ed)` keys fetch separately; a **rejected** load is NOT cached (retry refetches). Same for `loadQa`. Run to red, record for Red-before.

Implement: module-level `Map<string, Promise<…>>` keyed `${documentId}:${edition}`; delete the map entry on rejection before rethrowing. Keep signatures identical (the `signal` param on `loadQa`: drop per-call abort semantics for the shared cache consciously — pass no signal into the cached fetch and remove signal from the cache key; callers' AbortController usage stays harmless. Document this in the PR body.) Export a test-only `clearCache()` helper or accept a `Map` reset between tests via `vi.resetModules()`.

Verify: `pnpm --filter @atr/web run test` → green.

### Step 2 — Lift `GlossaryProvider` to `ReaderLayout`

Move the provider from `ReaderPage` (line 82) to wrap the layout's `<Outlet/>` region in `ReaderLayout.tsx` (it depends only on `documentId`/`edition`, both layout-level params). Remove it from `ReaderPage`, keep `PageGlossaryProvider` (per-page mentions) where it is. With Step 1's cache this is belt-and-braces, but lifting also stops the Map rebuild + provider churn.

Tests: extend `ReaderLayout.test.tsx` to assert glossary context is available to child routes; check `ReaderPage.test.tsx`'s existing 6 tests — they may wrap `ReaderPage` directly and need a provider in the test harness now.

Verify: `pnpm --filter @atr/web run test && pnpm --filter @atr/web run typecheck && pnpm --filter @atr/web run lint`.

### Step 3 — `QaPageBadge` dep split

Split the effect: fetch on `[documentId, edition]` storing the records (or rely on the Step-1 cache and keep one effect — simplest correct form: keep the single effect with all three deps; the cached promise makes re-runs free; derive the count in the `.then`). Prefer the minimal diff: with `loadQa` cached, the existing code becomes cheap — but still add the missing component test: badge shows count, hides at 0, hides on fetch failure (write all three; red-before via mocking `loadQa`).

Verify: `pnpm --filter @atr/web run test`.

### Step 4 — Replace the hash re-bounce with the S5U-584 highlight-class pattern

In `ReaderPage.tsx:51-62`: keep `scrollIntoView`, drop both `window.location.hash` assignments. Add a transient highlight class (e.g. `anchor-highlight`) to the matched element (add + remove on timeout, or rely on a CSS animation), and add the corresponding style in `apps/web/src/styles/` mirroring whatever `.glossary-card-highlight` does. Check which CSS rules currently use `:target` for reader anchors (`grep -rn ':target' apps/web/src/styles/`) and port them to the class.

Tests: new component test asserting `history.length` does not grow when mounting `ReaderPage` with a hash (this is the test that would have caught the bug; jsdom supports history). Red-before: run it against the unfixed component first.

Verify: `pnpm --filter @atr/web run test`.

### Step 5 — Index page: `Link` + error state

- Replace the raw `<a href>` page pills (`DocumentIndexPage.tsx:104`) with `<Link to={…}>` from `react-router` (same className/title; `Link` renders an `<a>`, so existing test selectors should survive — confirm in `DocumentIndexPage.test.tsx`).
- Add an `error` state set in the fetch `.catch`; render a distinct `role="alert"` message; keep "No documents found" only for a successful empty result. Component tests for both branches (red-before).

Verify: `pnpm --filter @atr/web run test`.

### Step 6 — Full gates + visual verification

```bash
make lint && make typecheck && make test
```
Then per `.claude/rules/visual-verify.md`: start the dev server on `localhost:3001`, and with Playwright MCP:
- Navigate index → click a page pill (confirm client-side transition), 
- Navigate between two reader pages and confirm glossary tooltips/links render immediately on the second page (no pop-in),
- Follow a QA-dashboard deep link to `pageId#entity_ref`, confirm the anchor highlight appears and **browser Back returns to the dashboard in one step**,
- Screenshot affected pages to `tmp/` and inspect.

Local Playwright e2e (optional but recommended): `pnpm --filter @atr/web run test:e2e` — expect visual snapshots to PASS unchanged on CI (macOS local runs may show font-hinting drift; CI is authoritative, per the platform note in visual-verify.md).

### Step 7 — Review per CLAUDE.md step 6 (independent fresh-eyes), then stop; push/PR only on user instruction.

## Test plan

- Loader caches: single-fetch per key, per-key isolation, rejection-not-cached (6 new tests, red-before each).
- `QaPageBadge`: count / zero-hide / failure-hide (3 new tests — first coverage for this component).
- ReaderPage hash effect: no history growth on anchor mount; element receives highlight class.
- DocumentIndexPage: error branch renders alert; empty-success renders "No documents found"; pills are router links.
- All existing component suites green; e2e suite green; CI visual baselines unchanged.

## Machine-checkable done criteria

- [ ] `grep -n "window.location.hash = ''" apps/web/src/routes/ReaderPage.tsx` → no match
- [ ] `grep -n "GlossaryProvider" apps/web/src/routes/ReaderLayout.tsx` → match; `grep -n "GlossaryProvider" apps/web/src/routes/ReaderPage.tsx` → no match
- [ ] `grep -n "<a$\|<a " apps/web/src/routes/DocumentIndexPage.tsx` → no raw anchor for page pills (Link used)
- [ ] `grep -n "Map<" apps/web/src/lib/api/loadGlossary.ts apps/web/src/lib/api/loadQa.ts` → cache present in both
- [ ] New test files/cases exist for QaPageBadge and the hash effect; `pnpm --filter @atr/web run test` → 0 failures
- [ ] `make lint && make typecheck && make test` → green
- [ ] CI `visual-regression / visual` green **without** baseline PNG changes
- [ ] PR body: Red-before lines for every new test, Coverage table row per issue bullet, visual-verification notes/screenshots

## STOP conditions

- STOP if the visual-regression gate fails on CI with pixel drift on curated pages — these fixes must not change static rendering; a diff means the highlight-class port (Step 4) altered anchor styling on a baseline page. Fix the CSS to match the old `:target` appearance rather than refreshing baselines; refresh baselines ONLY if the team confirms the new appearance is intended, in a dedicated commit.
- STOP if `ReaderLayout` turns out not to be the common parent for all routes that consume glossary context (grep `useGlossary`/`GlossaryContext` consumers first — e.g. `GlossaryPage` may have its own data path) — lifting must not create a duplicate or missing provider.
- STOP if dropping the `signal` from cached `loadQa` breaks `QaDashboard` behavior that depends on aborting in-flight loads (check `QaDashboard.tsx` usage before Step 1).
- STOP if any file approaches the 400-line oxlint cap.

## Maintenance notes

- The promise-cache pattern (module Map keyed by `${doc}:${edition}`, rejection evicted) is the house pattern for any future per-document static asset (manifests, qa_metrics) — `loadManifest`/`loadQaMetrics` are natural follow-ups if profiling shows churn.
- A follow-up e2e "navigation journey" test (index → page → next page → glossary deep link → Back) would pin all four behaviors at once; see the rejected-findings list in plans/README.md (web test-coverage finding).

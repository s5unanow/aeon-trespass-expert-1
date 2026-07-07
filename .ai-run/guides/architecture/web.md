# apps/web — Architecture Guide

React 19 / Vite 6 / React Router 7 static reader. It renders a pre-built
document bundle produced by the pipeline; there is no runtime backend. All data
is fetched as static JSON from `public/documents/...`, and all TypeScript data
types are generated from Pydantic (never hand-written).

Deep-detail rules live in `.claude/rules/web.md`, `.claude/rules/schemas.md`,
and `.claude/rules/visual-verify.md` — this guide summarizes structure and
points there rather than restating.

## Architecture Overview

The web app is a pure static reader: it fetches JSON artifacts by URL, narrows
them into reader-local shapes, and renders blocks/inlines. No server code, no
data mutation — feedback is exported as a client-side download, not POSTed.

### Static-bundle consumer, no backend

- Rule: treat the app as read-only over the exported bundle. Data access goes
  through `fetch()` of static paths under `/documents/...`; never introduce a
  server round-trip or write API.
- The single data-fetch shape is edition-path-first with a root fallback — see
  `apps/web/src/lib/api/loadRenderPage.ts:11` (`editionUrl` then `rootUrl`).
- Dev server is fixed to port 3001 (`apps/web/vite.config.ts:8`,
  `strictPort: true`); Playwright previews the built bundle on 4173
  (`apps/web/playwright.config.ts`).

## Component Structure

`src/` is layered: entry (`main.tsx`) → app shell (`app/`) → route pages
(`routes/`) → layout + reader + nav components (`components/`), with pure
helpers in `lib/` and cross-cutting state in `contexts/`.

| Dir | Responsibility | Example |
|-----|----------------|---------|
| `src/app/` | Router + `RouterProvider` shell | `apps/web/src/app/App.tsx`, `apps/web/src/app/router.tsx` |
| `src/routes/` | One component per URL page | `apps/web/src/routes/ReaderPage.tsx:15` |
| `src/components/reader/` | Block/inline renderers | `apps/web/src/components/reader/BlockRenderer.tsx` |
| `src/components/layout/` | Shell chrome (header, sidebar, layout) | `apps/web/src/components/layout/ReaderLayout.tsx` |
| `src/lib/api/` | Static-JSON loaders | `apps/web/src/lib/api/loadManifest.ts` |
| `src/lib/render/` | Schema→reader normalization | `apps/web/src/lib/render/normalize.ts` |
| `src/contexts/` | Glossary + page-scoped state | `apps/web/src/contexts/GlossaryContext.tsx:40` |

- `main.tsx` mounts `<App/>` under `StrictMode` and imports every stylesheet in
  order — `apps/web/src/main.tsx:4`.

## Routing

React Router 7 with `createBrowserRouter`. The URL shape is
`/documents/:documentId/:edition/:pageId`; `glossary` and `qa` are sibling
child routes under the same `:edition` layout.

- Route table: `apps/web/src/app/router.tsx:24` — `ReaderLayout` is the parent
  element, with `glossary`, `qa`, and `:pageId` children.
- The QA dashboard is `lazy()`-loaded so it stays out of the reader's initial
  bundle — `apps/web/src/app/router.tsx:9`.
- Params are read via `useParams<{documentId; edition; pageId}>()` — see
  `apps/web/src/routes/ReaderPage.tsx:15` and
  `apps/web/src/components/layout/ReaderLayout.tsx:20`.
- The `:edition` segment drives `<html lang>` through a single explicit map —
  `apps/web/src/lib/editionLang.ts` (`EDITION_LANG`), applied at
  `apps/web/src/components/layout/ReaderLayout.tsx:44`.

## Generated Types Contract

Contract direction is Python Pydantic → JSON Schema → generated TS in
`@atr/schemas` (`workspace:*`). Never hand-write a data type on the web side;
regenerate with `make codegen`. See `.claude/rules/schemas.md`.

- Import generated types only from the package root — e.g.
  `apps/web/src/lib/api/loadGlossary.ts:1`
  (`import type { GlossaryPayloadV1 } from '@atr/schemas'`).
- The package re-exports every generated module as a namespace; root is
  `packages/schemas/ts/src/index.ts:4`, generated sources live under
  `packages/schemas/ts/src/generated/render_page_v1.ts`.

| Do | Don't |
|----|-------|
| `import type { renderPageV1 } from '@atr/schemas'` (`apps/web/src/lib/render/types.ts:22`) | Declare an interface mirroring a JSON artifact by hand |
| Narrow generated (loose, defaulted) types locally with utility projections (`apps/web/src/lib/render/types.ts:31`) | Edit files under `packages/schemas/ts/**` (generated) |

- Additive-schema safety: new block/inline kinds land in the generated union
  and the exhaustive `switch` fails to compile on the `never` branch until
  wired — `apps/web/src/components/reader/BlockRenderer.tsx` (`_exhaustive: never`).

## Component & Styling Conventions

Components are single-responsibility and small; oxlint enforces a hard
400-line cap and forbids import cycles. Styling is plain CSS files with CSS
custom properties (design tokens) — no CSS-in-JS.

- `max-lines: 400` and `import/no-cycle: error` — `apps/web/.oxlintrc.json:13`
  and `apps/web/.oxlintrc.json:12`. Lint runs via `pnpm lint`
  (`oxlint --import-plugin .`).
- Block dispatch is a flat `switch` on a discriminant, one component per kind —
  `apps/web/src/components/reader/BlockRenderer.tsx:16`.
- Styles are token-driven: color/spacing variables in
  `apps/web/src/styles/tokens.css:1`, imported once (with `reset.css`,
  `reader.css`, etc.) in `apps/web/src/main.tsx:4`.
- Prefer `import type { ... }` for type-only imports to keep the module graph
  acyclic — e.g. `apps/web/src/components/reader/BlockRenderer.tsx:1`.

## Data Source

The bundle under `apps/web/public/documents/{doc}/{edition}/` is produced by
`scripts/export_to_web.py`. Each edition dir holds a `manifest.json` (page
list) plus `data/render_page.{pageId}.json`, glossary, and QA artifacts; the
export also writes a top-level `index.json`.

- Export entry + destination shape: `scripts/export_to_web.py:2`
  (`.../public/documents/{doc_id}/{edition}/`).
- Document index (list of docs + editions) written by
  `scripts/export_to_web.py:143` (`write_document_index`); the reader reads it
  via `apps/web/src/lib/api/loadDocumentIndex.ts`.
- Per-page fetch path: `data/render_page.{pageId}.json` —
  `apps/web/src/lib/api/loadRenderPage.ts:11`.
- Manifest shape (document_id, edition, pages[]): sample at
  `apps/web/public/documents/target_p0040/en/manifest.json`.
- Raw JSON is normalized before components see it — `normalizeRenderPage` in
  `apps/web/src/lib/render/normalize.ts` materializes defaulted fields so
  components skip null checks.

## Testing

Two tiers. Vitest (jsdom) drives unit + component tests; Playwright drives e2e
+ visual regression against the built preview. See
`.claude/rules/visual-verify.md` for the full baseline-update flow.

- Vitest config: jsdom env + include globs at `apps/web/vitest.config.ts:13`
  and `apps/web/vitest.config.ts:15` (`tests/**/*.test.{ts,tsx}`).
- Component tests live in `apps/web/tests/component/` (e.g.
  `BlockRenderer.test.tsx`); unit in `apps/web/tests/unit/`.
- Playwright `testDir` is `apps/web/tests/e2e` (`apps/web/playwright.config.ts:4`);
  specs `reader-page.spec.ts` + `extraction-regression.spec.ts`.
- Visual-regression threshold is `maxDiffPixelRatio: 0.005` —
  `apps/web/playwright.config.ts:17`. Baselines are committed PNGs under
  `apps/web/tests/e2e/__snapshots__/` (path template at
  `apps/web/playwright.config.ts:10`).
- Snapshot assertions use `toHaveScreenshot('...png')` —
  `apps/web/tests/e2e/extraction-regression.spec.ts:218`.
- Never add `--update-snapshots` / `-u` to a CI command; regenerate baselines
  locally via `pnpm --filter @atr/web run test:visual:update`
  (`apps/web/package.json` `test:visual:update`). CI is blocked from
  regenerating — see `.claude/rules/visual-verify.md`.

## Boundaries Summary

- DO fetch static JSON through `src/lib/api/*` loaders and normalize via
  `src/lib/render/*` before rendering (`apps/web/src/lib/api/loadRenderPage.ts:25`).
- DO import all data types from `@atr/schemas`; regenerate with `make codegen`
  after any Pydantic change (`.claude/rules/schemas.md`).
- DO keep each component under 400 lines and cycle-free (`apps/web/.oxlintrc.json:13`).
- DON'T hand-write TypeScript data types or edit `packages/schemas/ts/**`.
- DON'T add a backend/write API — feedback is a client-side download
  (`apps/web/src/lib/feedback/download.ts`).
- DON'T loosen the visual threshold or update snapshots in CI
  (`apps/web/playwright.config.ts:17`; `.claude/rules/visual-verify.md`).

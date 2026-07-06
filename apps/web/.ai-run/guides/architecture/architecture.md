# Architecture Guide — apps/web

**Project**: `@atr/web` (`apps/web/package.json:2`)
**Style**: Modular SPA — static-bundle reader, no backend of its own
**Language**: TypeScript | **Framework**: React 19 + React Router 7 + Vite 6

---

## Architecture Overview

`apps/web` renders a pre-built content bundle (JSON + images under `public/documents/**`,
produced by the pipeline's export stage) — it has no server-side API of its own. The app
is a client-side router over static `fetch()` calls, with a single normalization boundary
that converts loosely-typed generated schema JSON into strict reader-local types.

```
main.tsx -> App.tsx -> RouterProvider(router.tsx)
                          |
              +-----------+------------+
              |                        |
     DocumentIndexPage         ReaderLayout (route: /documents/:id/:edition)
                                          |
                          +---------------+---------------+
                          |               |               |
                    ReaderPage       GlossaryPage    QaDashboard (lazy)
                          |
                    BlockRenderer (switch on block.kind)
                          |
              HeadingBlock / ParagraphBlock / FigureBlock / TableBlock / ...
```

**Key decision**: routes fetch and normalize their own data (`loadRenderPage`,
`loadManifest`, `loadGlossary`); there is no global store. `ReaderLayout` owns only the
cross-page state that must survive page-to-page navigation (manifest, glossary) —
see `apps/web/src/components/layout/ReaderLayout.tsx:103-129`.

---

## Component Structure

```
apps/web/src/
├── app/            Router wiring: App.tsx, router.tsx (route tree, lazy QA dashboard)
├── routes/         Route-level containers: fetch + orchestrate (ReaderPage, DocumentIndexPage,
│                   GlossaryPage, QaDashboard)
├── components/
│   ├── layout/     Chrome shared across reader routes (ReaderLayout, AppHeader, PageSidebar)
│   ├── reader/     Block/inline renderers (BlockRenderer, InlineRenderer, *Block.tsx)
│   ├── nav/        Navigation/QA badges and cards
│   └── glossary/   Glossary entry presentation
├── contexts/       Cross-cutting React Context providers (GlossaryContext, PageContext)
├── lib/
│   ├── api/        fetch + cache wrappers for bundle JSON (loadRenderPage, loadManifest, ...)
│   ├── render/     Schema-to-reader type projection + runtime normalization
│   └── feedback/   Feedback submission shape + filename helper
└── styles/         One CSS file per concern (reader.css, layout.css, glossary.css, qa.css, ...)
```

---

## Design Patterns Detected

| Pattern | Usage | Location |
|---------|-------|----------|
| Anti-corruption layer / normalization boundary | Converts raw `unknown` JSON into a strict `RenderPageData` before any component sees it | `apps/web/src/lib/render/normalize.ts:329-368` |
| Discriminated union + exhaustive switch | `BlockRenderer` dispatches on `block.kind`; a `never` fallback fails to compile if a kind is unhandled | `apps/web/src/components/reader/BlockRenderer.tsx:16-39` |
| Context provider (lifted state) | `GlossaryProvider` lives in `ReaderLayout`, not `ReaderPage`, so the 213 KB glossary bundle survives per-page resets | `apps/web/src/components/layout/ReaderLayout.tsx:103` |
| Module-level promise cache | `loadGlossary` memoizes in-flight fetches per `documentId:edition`, evicting on rejection | `apps/web/src/lib/api/loadGlossary.ts:13-40` |
| Lazy route splitting | `QaDashboard` is `lazy()`-imported so its bundle doesn't load for reader sessions that never visit `/qa` | `apps/web/src/app/router.tsx:10-12` |
| Compile-time coverage tripwire | Type-level assertion flips to `never` (breaking the build) when the generated schema admits a `kind` not yet mirrored in the reader union | `apps/web/src/lib/render/types.ts:128-137` |

### Primary Pattern: schema projection + runtime normalization

```ts
// Source: apps/web/src/lib/render/normalize.ts:119-124
function normalizeBlock(raw: unknown, path: string): RenderBlock {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected block object, got ${typeof raw}`);
  }
  const id = asString(raw.id, `${path}.id`);
  const kind = asString(raw.kind, `${path}.kind`);
```

**When to use**: any time raw bundle JSON crosses into component code. `RenderPageData` and
its member types (`apps/web/src/lib/render/types.ts:176-189`) are the only shape components
are allowed to consume; `normalizeRenderPage` (`normalize.ts:329`) is the single call site
that performs the raw-to-typed conversion, materializing Pydantic-defaulted optional fields
into required ones and rejecting unknown block/inline kinds (S5U-685 "fail-fast on new kinds").

---

## Layer/Module Responsibilities

| Component | Responsibility | Depends On | Depended By |
|-----------|----------------|------------|-------------|
| `routes/` | Fetch data for a URL, own loading/error state | `lib/api`, `lib/render`, `components/` | `app/router.tsx` |
| `components/layout/` | Shared reader chrome, cross-page state (manifest, glossary) | `lib/api`, `contexts/` | `routes/` |
| `components/reader/` | Pure rendering of normalized block/inline data | `lib/render` (types only) | `routes/ReaderPage.tsx` |
| `lib/api/` | `fetch()` the static bundle, edition-fallback, caching | `@atr/schemas` (types only) | `routes/`, `components/layout/` |
| `lib/render/` | Project generated schema types -> reader types; normalize raw JSON | `@atr/schemas` | `lib/api/loadRenderPage.ts`, `components/reader/` |
| `contexts/` | Cross-cutting React state (glossary index, per-page mentions) | `lib/api/loadGlossary.ts` | `components/reader/`, `routes/GlossaryPage.tsx` |

---

## Dependency Rules

```
packages/schemas (Pydantic -> JSON Schema -> generated TS)
         │
         ▼
apps/web/src/lib/render/types.ts  ──►  lib/render/normalize.ts  ──►  components/reader/*
apps/web/src/lib/api/*.ts (fetch + cache, imports @atr/schemas types directly)
```

| Rule | Enforced By |
|------|-------------|
| No import cycles between modules | `import/no-cycle: error` — `apps/web/.oxlintrc.json:12` |
| No file over 400 lines | `eslint/max-lines` — `apps/web/.oxlintrc.json:13-20` |
| Reader components never read raw bundle JSON directly | Convention — every route goes through a `lib/api/load*` function that returns a typed/normalized result (e.g. `loadRenderPage` returns `RenderPageData`, never `unknown`) — `apps/web/src/lib/api/loadRenderPage.ts:9,25` |
| TypeScript types for the content bundle are never hand-written | Generated barrel `packages/schemas/ts/src/index.ts:1` ("Auto-generated barrel — do not edit") and per-schema files, e.g. `packages/schemas/ts/src/generated/render_page_v1.ts:1` ("Auto-generated from JSON Schema — do not edit") |

**Violations to avoid:**
- ❌ Adding a new block/inline `kind` to `normalize.ts` without adding the matching case to
  `BlockRenderer`/`InlineRenderer` — the compile-time tripwire in `types.ts:134-137` catches
  this, but a matching runtime `switch` case is still required in both files.
- ❌ Consuming `renderPageV1.*` generated types directly in a component instead of the
  narrowed `RenderBlock`/`RenderPageData` projection — the generated types still carry
  Pydantic-optional fields the reader has already normalized away.

---

## Data Flow

**Example flow** (loading a reader page):
1. `ReaderPage` mounts for route `/documents/:documentId/:edition/:pageId` and calls
   `loadRenderPage(documentId, pageId, edition, signal)` — `apps/web/src/routes/ReaderPage.tsx:32`.
2. `loadRenderPage` fetches the edition-specific JSON path, falling back to the
   document-root path on 404 — `apps/web/src/lib/api/loadRenderPage.ts:11-23`.
3. The raw JSON is passed to `normalizeRenderPage`, which validates and materializes it into
   `RenderPageData` — `apps/web/src/lib/api/loadRenderPage.ts:25`, `apps/web/src/lib/render/normalize.ts:329`.
4. `ReaderPage` renders `page.blocks.map(...)` through `BlockRenderer`, which dispatches to a
   leaf component per `block.kind` — `apps/web/src/routes/ReaderPage.tsx:106-113`,
   `apps/web/src/components/reader/BlockRenderer.tsx:16-39`.

---

## Key Abstractions

| Abstraction | Purpose | Implementations |
|-------------|---------|-----------------|
| `RenderBlock` (discriminated union) | Reader-local, fully-materialized block shape consumed by `BlockRenderer` | `apps/web/src/lib/render/types.ts:105-113` |
| `GlossaryShape` | Glossary lookup surface (`byIcon`, `byConcept`, `entries`, `edition`) shared via context | `apps/web/src/contexts/GlossaryContext.tsx:18-23` |
| `DocumentManifest` | Page list + offset for the sidebar and pagination | `apps/web/src/lib/api/loadManifest.ts:1-8` |

---

## Adding New Features

### To add a new block/inline kind emitted by the pipeline:

1. Extend the Pydantic model and regenerate (`make codegen`, per `.claude/rules/schemas.md`)
   — this updates `packages/schemas/ts/src/generated/render_page_v1.ts`.
2. Add a `Narrow*` projection type and include it in the `RenderBlock`/`RenderInlineNode`
   union — `apps/web/src/lib/render/types.ts:62-113`.
3. Add a `case` to `normalizeBlock`/`normalizeInline` — `apps/web/src/lib/render/normalize.ts:119-180`.
4. Add a `case` to `BlockRenderer`/`InlineRenderer` — `apps/web/src/components/reader/BlockRenderer.tsx:16-39`.
5. The compile-time tripwires (`types.ts:134-137`) fail the build if step 2 is skipped;
   the `never`-branch throw in `BlockRenderer.tsx:34-37` fails at runtime if step 4 is skipped.

### To add a new route:

Add an entry (or child entry) to the `createBrowserRouter` array —
`apps/web/src/app/router.tsx:23-50`. Routes needing cross-page state nest under
`ReaderLayout`; standalone routes (e.g. `DocumentIndexPage`) sit at the top level.

---

## Configuration & Environment

| Config Type | Location | Accessed Via |
|-------------|----------|--------------|
| Dev server | `apps/web/vite.config.ts:7` (`port: 3001, strictPort: true`) | `pnpm dev` |
| Path alias | `@/*` -> `src/*` | `apps/web/vite.config.ts:8-11`, `apps/web/tsconfig.json:14-16` |
| Content bundle | `apps/web/public/documents/**` (static JSON + images, gitignored pipeline output in production, checked-in fixtures here) | `lib/api/load*.ts` via relative `fetch('/documents/...')` |

There are no environment-variable-driven secrets or API base URLs — the reader only ever
fetches same-origin static paths under `/documents/**` and `/icons/**`.

---

## Boundaries Summary

| DO | DON'T |
|-------|----------|
| Import content-bundle types from `@atr/schemas` (`import type { renderPageV1 } from '@atr/schemas'` — `apps/web/src/lib/render/types.ts:22`) | Hand-write a TS type that mirrors a Pydantic model |
| Route all raw bundle JSON through `normalizeRenderPage` before it reaches a component | Read `unknown` fetch results directly in a route/component |
| Keep cross-page state (manifest, glossary) in `ReaderLayout`/context | Re-fetch immutable per-document data (e.g. glossary) on every page turn |
| Add new block kinds to `types.ts` + `normalize.ts` + `BlockRenderer` together | Add a case to only one of the three and rely on the tripwire alone |

---

## Quick Reference

| Need | Location | Pattern |
|------|----------|---------|
| Entry point | `apps/web/src/main.tsx` | - |
| Route tree | `apps/web/src/app/router.tsx` | `createBrowserRouter` |
| Bundle fetch + cache | `apps/web/src/lib/api/` | fetch + edition fallback |
| Schema-to-reader projection | `apps/web/src/lib/render/types.ts` | `Narrow*` type helpers |
| Runtime normalization | `apps/web/src/lib/render/normalize.ts` | validate + materialize |
| Cross-cutting state | `apps/web/src/contexts/` | React Context provider |
| Styling | `apps/web/src/styles/*.css` | one file per concern |

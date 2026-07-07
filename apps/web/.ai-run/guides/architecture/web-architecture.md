# Web Architecture — @atr/web

**Project**: @atr/web (apps/web)
**Style**: Static SPA reader — no backend; all data is a pre-compiled JSON bundle under `public/documents/`
**Language**: TypeScript | **Framework**: React 19 + Vite 6 + React Router 7

## Architecture Overview

```
public/documents/<docId>/<edition>/…  (pipeline-exported JSON + assets)
        │ fetch
        ▼
lib/api/load*.ts ──► lib/render/normalize.ts ──► routes/* ──► components/*
                        (materialize defaults,      (state,      (pure render)
                         reject unknown kinds)       effects)
```

**Key decision**: the reader renders a bundle produced by the Python pipeline (`make export` runs `scripts/export_to_web.py`, see `Makefile:44-50`). All types flow Pydantic → JSON Schema → generated TS in `@atr/schemas` — never manual TS types (`.claude/rules/web.md`, `.claude/rules/schemas.md` are authoritative).

## Component Structure

```
src/
├── app/          Router + App shell (router.tsx)
├── routes/       Page-level components: ReaderPage, DocumentIndexPage, GlossaryPage, QaDashboard
├── components/   layout/ (ReaderLayout, AppHeader, PageSidebar), reader/ (block renderers),
│                 nav/ (badges, EditionSwitcher, QA cards), glossary/
├── contexts/     GlossaryContext (document-scoped), PageContext (page-scoped mentions)
├── lib/api/      fetch wrappers over the public/documents bundle
├── lib/render/   runtime normalization + reader-local type projections
└── styles/       plain CSS files (tokens.css, reader.css, layout.css, …)
```

## Routing

Routes are declared with `createBrowserRouter` in `src/app/router.tsx:23-50`:

| Path | Element |
|---|---|
| `/` | `DocumentIndexPage` |
| `/documents/:documentId/:edition` | `ReaderLayout` (layout route, `<Outlet>`) |
| `…/:pageId` | `ReaderPage` |
| `…/glossary` | `GlossaryPage` |
| `…/qa` | `QaDashboard`, lazy-loaded behind `Suspense` so it stays out of the reader's initial bundle (`src/app/router.tsx:10-12`) |

`ReaderLayout` passes layout-derived data down via `<Outlet context={{ pageOffset }}>` (`src/components/layout/ReaderLayout.tsx:125`); `ReaderPage` reads it with `useOutletContext` (`src/routes/ReaderPage.tsx:20-21`).

## Data Loading from the Bundle

All fetches go through `src/lib/api/load*.ts`. Shared conventions:

| Rule | Evidence |
|---|---|
| Edition-specific URL first, fall back to root on 404; non-404 errors throw immediately | `src/lib/api/loadRenderPage.ts:11-23`, `src/lib/api/loadManifest.ts:14-33` |
| Raw JSON is `unknown` and passes through the normalizer before any component sees it | `src/lib/api/loadRenderPage.ts:24-25` |
| Immutable per-document payloads are cached as module-level promises; rejected loads are evicted so retries refetch | `src/lib/api/loadGlossary.ts:13-40` |
| Loaders accept an optional `AbortSignal` for effect cleanup | `src/lib/api/loadRenderPage.ts:8` |

## Normalization Boundary (lib/render)

`normalizeRenderPage` (`src/lib/render/normalize.ts:329-368`) is the single place that materializes Pydantic defaults and rejects unknown block/inline kinds with a path-carrying `InvalidRenderPageError`. Components consume the narrowed projection `RenderPageData` (`src/lib/render/types.ts:176-189`) — no defensive null checks downstream.

**Additive-schema tripwires** (the "new kind fails fast" invariant, S5U-685):

| Guard | Location |
|---|---|
| `UnionHasAllKinds` compile-time check — new generated block/inline kind breaks the build until mirrored | `src/lib/render/types.ts:134-135` |
| `AssertEnumCovered` on enum tables (`PRESENTATION_MODES`, annotation kinds) | `src/lib/render/normalize.ts:62-71` |
| Exhaustive `switch` with `never` default in the renderer | `src/components/reader/BlockRenderer.tsx:34-37` |

## Contexts

| Context | Scope | Purpose |
|---|---|---|
| `GlossaryProvider` / `useGlossaryShape` | Mounted in `ReaderLayout` (`src/components/layout/ReaderLayout.tsx:103`), NOT in `ReaderPage` — surviving the `page=null` reset avoids refetching the ~213 KB glossary on every page turn | icon/concept lookup maps built with `useMemo` (`src/contexts/GlossaryContext.tsx:58-68`) |
| `PageGlossaryProvider` / `usePageGlossaryMentions` | Per page (`src/routes/ReaderPage.tsx:93`) | avoids prop-drilling `glossary_mentions` through every block kind (`src/contexts/PageContext.tsx:13-26`) |

## Render Pipeline (components/reader)

`ReaderPage` fetches → `BlockRenderer` dispatches on `block.kind` to one component per kind (`src/components/reader/BlockRenderer.tsx:17-33`) → block components render inlines via `InlineRenderer`. Facsimile pages short-circuit to `FacsimilePage` when `presentation_mode === 'facsimile'` (`src/routes/ReaderPage.tsx:99-104`).

## Boundaries Summary

| Do | Don't |
|---|---|
| Add new block kinds in Pydantic, run `make codegen`, then extend the tripwired unions/switches | Hand-edit `packages/schemas/ts/` or write manual TS types |
| Fetch only via `lib/api`, normalize via `lib/render` | `fetch` + cast raw JSON inside a component |
| Put document-scoped state in `ReaderLayout`-level providers | Mount providers below a component that resets to `null` on navigation |
| Lazy-load rarely visited routes (`router.tsx:10`) | Grow the initial reader bundle |

## Quick Reference

| Need | Location |
|---|---|
| Entry point | `src/main.tsx`, `src/app/router.tsx` |
| Data loaders | `src/lib/api/` |
| Normalizer + reader types | `src/lib/render/` |
| Block/inline renderers | `src/components/reader/` |
| Layout + nav chrome | `src/components/layout/`, `src/components/nav/` |
| Exported bundle (regenerate, don't edit) | `apps/web/public/documents/` via `make export` |

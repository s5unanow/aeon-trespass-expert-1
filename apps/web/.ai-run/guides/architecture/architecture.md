# Architecture Guide

**Project**: `@atr/web` (apps/web)
**Style**: Static SPA reader — layered (routes → components → lib → generated schemas), no backend
**Language**: TypeScript (strict) | **Framework**: React 19 + Vite 6 + React Router 7

Authoritative repo rules: `.claude/rules/web.md`, `.claude/rules/schemas.md`,
`.claude/rules/visual-verify.md`. This guide summarizes them with module evidence;
the rules files win on any conflict.

## Architecture Overview

The web app is a static reader for pipeline-exported document bundles. There is no
server API: all data is typed JSON fetched from `public/documents/` (populated by
`scripts/export_to_web.py` at the repo root).

```
public/documents/<docId>/<edition>/data/*.json   (pipeline export bundle)
        │ fetch
        ▼
src/lib/api/load*.ts        (fetch + edition→root fallback)
        │ raw unknown JSON
        ▼
src/lib/render/normalize.ts (runtime validation, defaults materialized)
        │ RenderPageData (narrowed types)
        ▼
src/routes/*  ──►  src/components/**  (exhaustive switch per block/inline kind)
```

**Key decision**: types flow one way — Python Pydantic → JSON Schema → generated TS
in `@atr/schemas` (`packages/schemas/ts/src/generated/`). The reader never hand-writes
schema types; it *narrows* generated types and validates at the fetch boundary
(`src/lib/render/types.ts:1-20`).

## Component Structure

```
apps/web/src/
├── main.tsx            Entry: createRoot + global CSS imports (src/main.tsx:13)
├── app/                App shell + router (src/app/router.tsx:23-50)
├── routes/             Route screens: ReaderPage, DocumentIndexPage, GlossaryPage, QaDashboard
├── components/
│   ├── layout/         ReaderLayout (Outlet host), AppHeader, PageSidebar
│   ├── reader/         One component per block/inline kind (BlockRenderer dispatch)
│   ├── nav/            Badges, EditionSwitcher, QaMetricsCards
│   └── glossary/       GlossaryEntryCard
├── contexts/           GlossaryContext, PageContext (React context providers)
├── lib/
│   ├── api/            Bundle loaders (fetch JSON from /documents/…)
│   ├── render/         normalize + reader-local type projections
│   ├── feedback/       Feedback download/schema helpers
│   └── editionLang.ts  Route :edition → <html lang> map (src/lib/editionLang.ts:33)
└── styles/             Plain CSS files, imported once in main.tsx
```

## Routing (React Router 7)

Defined in `src/app/router.tsx:23-50` via `createBrowserRouter`:

| Path | Element |
|---|---|
| `/` | `DocumentIndexPage` |
| `/documents/:documentId/:edition` | `ReaderLayout` (layout route with `Outlet`) |
| `…/:pageId` | `ReaderPage` |
| `…/glossary` | `GlossaryPage` |
| `…/qa` | `QaDashboard` — lazy-loaded so the reader bundle stays lean (`src/app/router.tsx:10-12`) |

`ReaderLayout` owns cross-page state: manifest fetch for the sidebar
(`src/components/layout/ReaderLayout.tsx:29-42`), `<html lang>` per edition
(`src/components/layout/ReaderLayout.tsx:49-55`), and the shared `GlossaryProvider`
(lifted there in S5U-1225 so page turns don't tear it down —
`src/routes/ReaderPage.tsx:90-93`).

## Generated-types dependency (@atr/schemas)

| Rule | Evidence |
|---|---|
| Depend on `@atr/schemas` (workspace pkg), never hand-write schema types | `package.json:26`; `.claude/rules/web.md` |
| Narrow generated loose types into reader projections, don't redefine them | `src/lib/render/types.ts:22` imports `renderPageV1`; `RenderPageData` at `src/lib/render/types.ts:176-189` |
| Compile-time tripwire: new block/inline kind in the schema breaks the build until wired | `UnionHasAllKinds` constants `src/lib/render/types.ts:134-135` |
| Runtime tripwire: unknown kinds rejected at the fetch boundary | `src/lib/render/normalize.ts:107` (inline), `:178` (block) |
| Exhaustive `switch` with `never` branch in renderers | `src/components/reader/BlockRenderer.tsx:35`, `src/components/reader/InlineRenderer.tsx:22` |

Contexts also consume generated types directly, e.g. `glossaryPayloadV1.GlossaryEntryV1`
(`src/contexts/GlossaryContext.tsx:2-5`).

## Dependency Rules

```
routes/ ──► components/ ──► lib/ ──► @atr/schemas (generated, read-only)
   │             │
   └─────────────┴──► contexts/
```

| Rule | Enforced By |
|---|---|
| No import cycles anywhere | oxlint `import/no-cycle: error` (`.oxlintrc.json:12`) |
| `lib/` is React-free data code (fetch, normalize, pure helpers) | Convention — see `src/lib/render/normalize.ts`, `src/lib/editionLang.ts:43` |
| Components consume post-normalization types only, no defensive null checks | `src/lib/render/types.ts:8-13` doc contract |
| Never edit `packages/schemas/ts/**` by hand | `.claude/rules/schemas.md` — regenerate via `make codegen` |

**Violations to avoid:**
- Reading raw fetched JSON in a component instead of going through a `lib/api` loader + normalizer.
- Adding a manual interface that mirrors a schema payload (see `.claude/rules/web.md`).

## Data Flow — rendering a reader page

1. Route match `/documents/:documentId/:edition/:pageId` mounts `ReaderPage`.
2. Effect fetches the page with abort + stale guards (`src/routes/ReaderPage.tsx:26-43`).
3. `loadRenderPage` tries the edition path, falls back to the root path on 404 only
   (`src/lib/api/loadRenderPage.ts:11-19`).
4. `normalizeRenderPage` validates `schema_version` (`src/lib/render/normalize.ts:45`),
   materializes defaults, rejects unknown kinds (`src/lib/render/normalize.ts:329-368`).
5. `BlockRenderer` dispatches each block to its component
   (`src/components/reader/BlockRenderer.tsx:17-38`); facsimile pages short-circuit to
   `FacsimilePage` (`src/routes/ReaderPage.tsx:99-104`).

## Adding New Features

### New block or inline kind (schema-driven)

1. Add the kind to the Pydantic model (`packages/schemas/python/`), run `make codegen`.
2. Compilation now fails at the tripwires (`src/lib/render/types.ts:134-135`) — extend the
   reader projection union.
3. Add the `case` to `normalizeBlock`/`normalizeInline` (`src/lib/render/normalize.ts:125-179`).
4. Add the `case` + component in `src/components/reader/` and wire it in
   `BlockRenderer.tsx` / `InlineRenderer.tsx`.
5. Add component tests plus e2e/visual coverage if it renders on curated pages.

### New route

1. Add a screen under `src/routes/`, register in `src/app/router.tsx:23-50`.
2. Lazy-load it if it's off the reader hot path (pattern: `src/app/router.tsx:10-12`).

## Configuration & Environment

| Config | Location | Notes |
|---|---|---|
| Dev server | `vite.config.ts:7` | port 3001, `strictPort` (visual-verify rule expects `localhost:3001`) |
| Path alias `@ → src` | `vite.config.ts:8-12`, `tsconfig.json:14-16` | keep in sync with `vitest.config.ts:7-11` |
| E2E/preview server | `playwright.config.ts:29-33` | builds then serves on port 4173 |
| Content data | `public/documents/`, `public/icons/` | exported fixtures/bundles; no env vars, no secrets |

## Boundaries Summary

| ✅ DO | ❌ DON'T |
|---|---|
| Import schema types from `@atr/schemas` | Hand-write TS types for pipeline payloads |
| Validate JSON in `lib/render/normalize*` at the fetch boundary | Cast `unknown` JSON to a type in a component |
| Keep block components single-kind, single-responsibility | Grow multi-kind mega-components past 400 lines (`.oxlintrc.json:13-20`) |
| Use exhaustive `switch` + `never` for kind dispatch | Add a `default: return null` that swallows new kinds |

## Quick Reference

| Need | Location |
|---|---|
| Entry point | `src/main.tsx` |
| Routes | `src/app/router.tsx` |
| Data loaders | `src/lib/api/` |
| Runtime validation | `src/lib/render/normalize.ts` |
| Reader type projections | `src/lib/render/types.ts` |
| Block components | `src/components/reader/` |
| Shared state | `src/contexts/` |
| Generated schema types | `packages/schemas/ts/src/generated/` (repo root; read-only) |

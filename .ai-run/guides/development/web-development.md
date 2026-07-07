# Web Development Practices (apps/web)

**Language**: TypeScript | **Framework**: React 19, Vite 6, React Router 7 (`apps/web/package.json:19-21`)

---

## Component Conventions

Component files are focused and single-responsibility, organized by feature under `apps/web/src/components/{reader,layout,nav,glossary}/` and `apps/web/src/routes/` for route-level components (`.claude/rules/web.md`).

Route components fetch data in a `useEffect`, guard against stale/aborted responses with `AbortController`, and clear state before refetching:

```tsx
// Source: apps/web/src/routes/ReaderPage.tsx:25-38
useEffect(() => {
  if (!documentId || !pageId || !edition) return;
  const controller = new AbortController();
  let stale = false;
  setPage(null);
  setError(null);
  loadRenderPage(documentId, pageId, edition, controller.signal)
    .then((data) => { if (!stale) setPage(data); })
    .catch((e) => { if (!stale && e.name !== 'AbortError') setError(e.message); });
  return () => { stale = true; controller.abort(); };
}, [...]);
```

---

## Routing

Routes are registered in `apps/web/src/app/router.tsx` via `createBrowserRouter`. Routes off the primary reading path are lazy-loaded so they don't affect the reader's initial bundle:

```tsx
// Source: apps/web/src/app/router.tsx:9-11
const QaDashboard = lazy(() =>
  import('../routes/QaDashboard').then((m) => ({ default: m.QaDashboard })),
);
```

---

## Types

**Never** write a TypeScript type by hand for data crossing the pipeline/web boundary — all such types are generated from Pydantic via `make codegen` into `packages/schemas/ts/src/generated/`. Purely UI-local types (component props, local state) are hand-written as normal.

---

## Code Quality

| Tool | Config | Command |
|------|--------|---------|
| Lint | `apps/web/.oxlintrc.json` | `pnpm --filter @atr/web lint` |
| Type check | `apps/web/tsconfig.json` | `pnpm --filter @atr/web typecheck` |
| Format | `.prettierrc.json` | `pnpm --filter @atr/web format` |

Enforced oxlint rules (`apps/web/.oxlintrc.json:4-16`): `import/no-cycle: error`, `max-lines: 400` (blank lines/comments excluded), `no-unused-vars: warn` (params prefixed `_` are exempt).

---

## Quick Reference

| Need | Location |
|------|----------|
| Route components | `apps/web/src/routes/` |
| Feature components | `apps/web/src/components/` |
| API loaders | `apps/web/src/lib/api/` |
| Router wiring | `apps/web/src/app/router.tsx` |
| Generated types (never hand-edit) | `packages/schemas/ts/src/generated/` |
| Lint config | `apps/web/.oxlintrc.json` |

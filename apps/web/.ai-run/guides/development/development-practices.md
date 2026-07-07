# Development Practices — @atr/web

**Language**: TypeScript (strict, `tsc --noEmit`) | **Framework**: React 19
**Linter**: oxlint | **Formatter**: prettier 3

Path-level conventions in `.claude/rules/web.md` are authoritative; this guide records how they show up in the code.

## Code Style

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Component files | PascalCase `.tsx`, one component per file | `src/components/reader/BlockRenderer.tsx` |
| Lib/util files | camelCase `.ts` | `src/lib/editionLang.ts`, `src/lib/api/loadRenderPage.ts` |
| Components / types | PascalCase | `ReaderLayout` (`src/components/layout/ReaderLayout.tsx:19`) |
| Functions / hooks | camelCase, hooks prefixed `use` | `useGlossaryShape` (`src/contexts/GlossaryContext.tsx:83`) |
| Module constants | UPPER_SNAKE_CASE | `ANCHOR_HIGHLIGHT_MS` (`src/routes/ReaderPage.tsx:12`), `ICON_MAP` (`src/components/reader/IconInline.tsx:9`) |

### Code Quality Commands

| Action | Command | Config |
|---|---|---|
| Lint | `pnpm lint` (`oxlint --import-plugin .`) | `apps/web/.oxlintrc.json` |
| Format | `pnpm format` (prettier writes `src/**/*.{ts,tsx,css}`) | `apps/web/package.json:11` |
| Type check | `pnpm typecheck` (`tsc --noEmit`) | `apps/web/tsconfig.json` |

Enforced oxlint rules: `import/no-cycle: error` (`.oxlintrc.json:12`) and `eslint/max-lines` max 400 (`.oxlintrc.json:13-19`) — keep files single-responsibility and split before hitting the cap. These run in the repo pre-commit hook and CI; see CLAUDE.md § Quality gates.

## Generated-Types Discipline

Never write manual TS types for pipeline data — the contract direction is Pydantic → JSON Schema → generated TS (`.claude/rules/schemas.md`, authoritative).

| Avoid | Prefer |
|---|---|
| Hand-declaring an interface for bundle JSON | Import from `@atr/schemas` and narrow it, as `src/lib/render/types.ts:22-56` does with `NarrowKind`/`NarrowBlock` |
| Casting `await res.json()` to a type | Normalize `unknown` at the fetch boundary (`src/lib/render/normalize.ts:329`) |
| Silently absorbing a new schema kind | Rely on the compile-time tripwires (`src/lib/render/types.ts:134-135`) and `never`-default switches (`src/components/reader/BlockRenderer.tsx:34-37`) |

After any Pydantic change run `make codegen`; the codegen helper fails loud on schemas it cannot map (pinned by `tests/unit/generateTsTypes.test.ts:1-10`).

## React Patterns

### Async in Effects — stale-flag + AbortController

Every data-loading effect guards against races on param change:

```tsx
// src/routes/ReaderPage.tsx:28-42 (abridged)
const controller = new AbortController();
let stale = false;
loadRenderPage(documentId, pageId, edition, controller.signal)
  .then((data) => { if (!stale) setPage(data); });
return () => { stale = true; controller.abort(); };
```

The lighter stale-flag-only form is used where abort is unnecessary (`src/contexts/GlossaryContext.tsx:43-56`).

### Other observed conventions

| Pattern | Evidence |
|---|---|
| Context value memoized with `useMemo`; React 19 `<Context value={...}>` (no `.Provider`) | `src/contexts/GlossaryContext.tsx:58-70` |
| Providers placed at the shallowest level that owns their inputs, so navigation resets don't tear them down | `src/components/layout/ReaderLayout.tsx:98-103` |
| `lazy()` + `Suspense` for routes off the hot path | `src/app/router.tsx:10-12` |
| Event handlers passed to effects wrapped in `useCallback` | `src/components/layout/ReaderLayout.tsx:71-87` |
| Loading states as accessible skeletons (`aria-busy`, `aria-label`), errors as `role="alert"` | `src/routes/ReaderPage.tsx:72-87` |
| Load-bearing decisions explained in comments citing the Linear issue | `src/routes/ReaderPage.tsx:46-54` (history-entry bug), `ReaderLayout.tsx:98-102` |

## Error Handling

| Case | Pattern | Source |
|---|---|---|
| Required data fails | Throw `Error` naming status + URL; route component renders `role="alert"` | `src/lib/api/loadRenderPage.ts:15-23`, `src/routes/ReaderPage.tsx:72-74` |
| Malformed payload | Typed `InvalidRenderPageError` with JSON path context | `src/lib/render/normalize.ts:43,107` |
| Best-effort data (glossary, manifest) | Catch, `console.warn` with context, degrade gracefully — never swallow silently | `src/contexts/GlossaryContext.tsx:50-52` |
| Aborted fetch | Filter `AbortError` before surfacing | `src/routes/ReaderPage.tsx:36-38` |

## Don't Do

| Avoid | Instead | Why |
|---|---|---|
| Importing across component layers into a cycle | Keep `lib/` free of component imports | `import/no-cycle` is an error (`.oxlintrc.json:12`) |
| Growing a file past ~400 lines | Split (e.g. normalize is split into `normalize.ts` / `normalize_primitives.ts` / `normalize_table.ts`) | `eslint/max-lines` cap |
| Editing `apps/web/public/documents/` by hand | `make export` regenerates it from pipeline artifacts | It is generated output |
| Editing `packages/schemas/ts/` | `make codegen` | Generated from Pydantic (`.claude/rules/schemas.md`) |
| Bouncing `window.location.hash` for anchor highlights | Transient CSS class | Pushes spurious history entries (`src/routes/ReaderPage.tsx:46-54`) |

## Workflow

Branching, commit prefixes (`S5U-XXX:`), review, and merge discipline are repo-wide — see AGENTS.md § Development workflow. Rendering-affecting changes additionally require the visual verification flow in `.claude/rules/visual-verify.md`.

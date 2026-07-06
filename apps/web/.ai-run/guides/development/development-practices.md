# Development Practices

**Project**: `@atr/web` (apps/web)
**Language**: TypeScript (strict) | **Framework**: React 19 + Vite 6 + React Router 7
**Linter**: oxlint | **Formatter**: prettier (repo-root `.prettierrc.json`)

Authoritative repo rules: `.claude/rules/web.md`, `.claude/rules/schemas.md`, and the
repo-root `CLAUDE.md` workflow. This guide summarizes them; the rules files win on any
conflict.

## Types: Generated, Never Manual

The single most important rule in this module (`.claude/rules/web.md`,
`.claude/rules/schemas.md`): the contract direction is Python Pydantic → JSON Schema →
generated TS. Regenerate with `make codegen` (repo root); never edit
`packages/schemas/ts/` or `packages/schemas/jsonschema/` by hand.

| Avoid | Prefer |
|---|---|
| Hand-writing an interface for a pipeline payload | Import from `@atr/schemas` — `src/contexts/GlossaryContext.tsx:2-5` |
| Redefining generated types loosely | Narrow them with utility projections — `src/lib/render/types.ts:22-56` |
| Casting fetched `unknown` JSON to a type | Validate at the fetch boundary — `src/lib/render/normalize.ts:329` |
| `default:` branches that swallow new schema kinds | Exhaustive `switch` + `never` — `src/components/reader/BlockRenderer.tsx:35` |

Compile-time tripwires (`src/lib/render/types.ts:134-135`) intentionally break the build
when the generated schema gains a kind the reader doesn't handle. Fix by extending the
union, never by deleting the tripwire.

## Code Style

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Component files | `PascalCase.tsx`, named exports | `src/components/reader/BlockRenderer.tsx` |
| Lib/helper files | `camelCase.ts` | `src/lib/api/loadRenderPage.ts` |
| Components / types | `PascalCase` | `ReaderPage` (`src/routes/ReaderPage.tsx:14`) |
| Functions / vars | `camelCase` | `langForEdition` (`src/lib/editionLang.ts:43`) |
| Module constants | `UPPER_SNAKE_CASE` | `ANCHOR_HIGHLIGHT_MS` (`src/routes/ReaderPage.tsx:12`) |
| CSS classes | `kebab-case`, `reader-`/`skeleton-` prefixes | `src/styles/reader.css` |

### Single-Responsibility Components

`.claude/rules/web.md`: component files are focused and single-responsibility. The
pattern here is one component per render concern — one file per block kind under
`src/components/reader/` (e.g. `TableBlock.tsx`, `CalloutBlock.tsx`), dispatched by the
`BlockRenderer` switch (`src/components/reader/BlockRenderer.tsx:17-38`). Don't grow a
component to handle multiple kinds; add a new file and a new `case`.

## Code Quality Gates

### Commands (from `package.json:10-16`)

| Action | Command |
|---|---|
| Lint | `pnpm --filter @atr/web run lint` (`oxlint --import-plugin .`) |
| Type check | `pnpm --filter @atr/web run typecheck` (`tsc --noEmit`) |
| Format (write) | `pnpm --filter @atr/web run format` (prettier over `src/**/*.{ts,tsx,css}`) |
| Unit/component tests | `pnpm --filter @atr/web run test` |
| Everything (repo-wide) | `make check` at repo root |

### Configuration

| Tool | Config | Key rules |
|---|---|---|
| oxlint | `.oxlintrc.json` | `import/no-cycle: error` (`:12`); `eslint/max-lines` max 400 (`:13-20`); unused args must be `_`-prefixed (`:5-11`) |
| tsc | `tsconfig.json` | `strict: true` (`:8`), `noEmit` (`:11`) — build is `tsc -b && vite build` |
| prettier | `.prettierrc.json` (repo root) | single quotes, trailing commas, printWidth 100 |

### Pre-commit / CI

The repo-level pre-commit hook (`.claude/hooks/pre-commit-check.sh`) runs oxlint and
`tsc --noEmit` on every commit; CI (`web / test`, `visual-regression / visual`) must be
green before merge. Never bypass hooks without disclosure — see the CLAUDE.md NEVER list.

## Error Handling

| Pattern | Rule | Source |
|---|---|---|
| Typed boundary error | Throw `InvalidRenderPageError` with a JSON path from normalizers | `src/lib/render/normalize.ts:43` (re-export), usage `:107`, `:178` |
| HTTP failures | Throw with status + URL; only 404 triggers the root-path fallback | `src/lib/api/loadRenderPage.ts:14-23` |
| Route-level display | Render `role="alert"` on error, skeleton while loading | `src/routes/ReaderPage.tsx:72-87` |
| Best-effort loads | Non-blocking data (manifest, glossary) may catch-and-warn, never catch-and-ignore blocking data | `src/contexts/GlossaryContext.tsx:51`; `src/components/layout/ReaderLayout.tsx:36-38` |

## Async / Data-Fetching Pattern

Canonical effect shape — `src/routes/ReaderPage.tsx:26-43`:

1. Guard on missing route params.
2. Create an `AbortController` and a `stale` flag.
3. Pass `controller.signal` down to the loader (`src/lib/api/loadRenderPage.ts:8`).
4. Ignore `AbortError`; only set state when `!stale`.
5. Cleanup sets `stale = true` and aborts.

Use this shape for any new loader-backed screen; it prevents state updates after
unmount and races on fast page turns.

## Visual-Affecting Changes

Any change to `src/components/**`, `src/routes/**`, or `src/styles/**` must be verified
visually before PR (dev server on `localhost:3001`, `vite.config.ts:7`) and may require a
local visual-baseline refresh — procedure and CI enforcement in
`.claude/rules/visual-verify.md`. Never add snapshot-update flags to CI.

## Git Workflow (summary — CLAUDE.md is authoritative)

- Branch: `s5unanow/s5u-XXX-short-description` off `main`; never commit to `main`.
- Commits: `S5U-XXX: description` (Linear issue prefix).
- New tests need red-before evidence (`.claude/rules/hooks.md`).
- PR requires the independent fresh-eyes review and green CI (all gates).

## Don't Do

| ❌ Avoid | ✅ Instead | Why |
|---|---|---|
| Manual TS types for schema payloads | Import + narrow `@atr/schemas` (`src/lib/render/types.ts:22`) | Single source of truth is Pydantic |
| Editing `packages/schemas/ts/**` | `make codegen` at repo root | Generated files are overwritten |
| Files > 400 lines | Split by responsibility | `.oxlintrc.json:13-20` errors |
| Import cycles | Respect routes → components → lib layering | `.oxlintrc.json:12` errors |
| `pnpm test:visual:update` in CI or workflow YAML | Local run + committed PNGs | Visual gate bypass — CI blocks it |
| Silent `.catch(() => {})` on blocking data | Surface via error state (`src/routes/ReaderPage.tsx:72-74`) | Errors must be visible to the user |

## Quick Reference

| Need | Location |
|---|---|
| Lint config | `apps/web/.oxlintrc.json` |
| Formatter config | `.prettierrc.json` (repo root) |
| TS config | `apps/web/tsconfig.json` |
| Boundary error class | `src/lib/render/normalize_primitives.ts` (re-exported from `normalize.ts:43`) |
| Canonical async pattern | `src/routes/ReaderPage.tsx:26-43` |
| Authoritative rules | `.claude/rules/web.md`, `.claude/rules/schemas.md`, `.claude/rules/visual-verify.md` |

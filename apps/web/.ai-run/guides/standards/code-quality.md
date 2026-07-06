# Code Quality Standards — apps/web

**Project**: `@atr/web`
**Linter**: oxlint 1.57 — `apps/web/.oxlintrc.json`
**Formatter**: prettier 3.4 — `.prettierrc.json` (repo root)
**Type Checker**: TypeScript 6, `strict: true` — `apps/web/tsconfig.json`

---

## Quality Commands

| Action | Command | Description |
|--------|---------|--------------|
| Lint | `pnpm lint` (`oxlint --import-plugin .` — `apps/web/package.json:10`) | Check code issues, including import cycles |
| Format | `pnpm format` (`prettier --write "src/**/*.{ts,tsx,css}"` — `apps/web/package.json:11`) | Format code |
| Type check | `pnpm typecheck` (`tsc --noEmit` — `apps/web/package.json:12`) | Verify types without emitting |
| Build (includes project-referenced typecheck) | `pnpm build` (`tsc -b && vite build` — `apps/web/package.json:8`) | Compile + bundle |

**Before committing, run**: the repo-root `make check` aggregate (lint + typecheck + test),
which wraps these `pnpm` commands via the pre-commit hook.

---

## Enforced Rules

### From Linter (`apps/web/.oxlintrc.json`)

| Rule | Setting | Rationale |
|------|---------|-----------|
| `import/no-cycle` | `error` | No cyclic module dependencies — `.oxlintrc.json:12` |
| `eslint/max-lines` | `error`, `max: 400`, blank lines/comments skipped | File-length cap — `.oxlintrc.json:13-20` |
| `eslint/no-unused-vars` | `warn`, `args: "after-used"`, `argsIgnorePattern: "^_"` | Unused-arg tolerance for intentionally-ignored params prefixed `_` — `.oxlintrc.json:5-11` |

### From Formatter (`.prettierrc.json`)

| Setting | Value |
|---------|-------|
| Line length | `100` |
| Indentation | 2 spaces |
| Quotes | single |
| Trailing comma | `all` |
| Semicolons | yes |

---

## Type Safety

**Strictness**: `strict: true` — `apps/web/tsconfig.json:8`
**Config**: `apps/web/tsconfig.json` (app), `apps/web/tsconfig.node.json` (tooling)

Runtime-unknown data (fetched JSON) is typed `unknown` and narrowed through explicit
assertion helpers rather than cast with `any`:

```ts
// Source: apps/web/src/lib/render/normalize_primitives.ts:29-38
export function asString(v: unknown, path: string, fallback?: string): string {
  if (v === undefined || v === null) {
    if (fallback !== undefined) return fallback;
    throw new InvalidRenderPageError(path, 'missing required string');
  }
  if (typeof v !== 'string') throw new InvalidRenderPageError(path, `expected string, got ${typeof v}`);
  return v;
}
```

### Type Rules

| Rule | Required |
|------|----------|
| Function parameters | Always (`strict` mode) |
| Function returns | Always |
| Raw external data | `unknown`, narrowed via `normalize_primitives.ts` helpers, never `any` |
| Generated schema types | Never hand-written — see `packages/schemas/ts/src/generated/*.ts:1` ("Auto-generated from JSON Schema — do not edit") |

---

## Code Complexity Limits

| Metric | Limit | Enforced By |
|--------|-------|-------------|
| File length | 400 lines | `eslint/max-lines` — `apps/web/.oxlintrc.json:13-20` |
| Import cycles | None allowed | `import/no-cycle` — `apps/web/.oxlintrc.json:12` |

### Reduce Complexity

`normalize.ts` sits at 368 lines against the 400-line cap; its table-child normalization
logic was already extracted to a sibling module to stay under the limit:

```ts
// Source: apps/web/src/lib/render/normalize_primitives.ts:1-5
/**
 * Primitive parse/assert helpers shared by `normalize.ts` and
 * `normalize_table.ts`. Extracted to keep each normalizer under the
 * 400-line file-length cap (S5U-704).
 */
```

Precedent: when a normalizer/renderer file approaches the cap, extract a focused sibling
module (e.g. `normalize_table.ts`, `normalize_primitives.ts`) rather than raising the limit.

---

## Documentation Standards

### Required Documentation

| Element | Required | Format |
|---------|----------|--------|
| Exported functions/types with non-obvious behavior | Yes | JSDoc-style `/** ... */` block above the declaration |
| Module-level invariants (normalization boundaries, fail-fast contracts) | Yes | File-header block comment |

### Format

```ts
// Source: apps/web/src/lib/render/types.ts:1-20
/**
 * Schema-derived render types for the reader.
 *
 * All types are mechanically projected from the generated `@atr/schemas`
 * package — the single source of truth is Python Pydantic, via JSON Schema,
 * to the generated TS in `packages/schemas/ts/src/generated/render_page_v1.ts`.
 * ...
 */
```

---

## Common Violations & Fixes

| Violation | Fix |
|-----------|-----|
| `eslint/no-unused-vars`: unused function argument | Prefix the argument with `_` (matches `argsIgnorePattern: "^_"`, `.oxlintrc.json:9`) rather than deleting a required positional param |
| `import/no-cycle`: cyclic import between two modules | Extract the shared piece into a new module both sides import (same pattern as `normalize_primitives.ts` splitting out of `normalize.ts`) |
| `eslint/max-lines`: file exceeds 400 lines | Split into focused sibling modules, e.g. `normalize.ts` / `normalize_table.ts` / `normalize_primitives.ts` |
| Manually-written type mirroring a Pydantic model | Delete it; import the generated type from `@atr/schemas` instead (e.g. `import type { renderPageV1 } from '@atr/schemas'` — `apps/web/src/lib/render/types.ts:22`) |

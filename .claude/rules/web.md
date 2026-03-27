---
description: React/TypeScript frontend conventions — applies to apps/web/
globs: apps/web/**
---

- React 19 with Vite and React Router 7
- Never create manual TypeScript types — all types generated from Pydantic via JSON Schema
- oxlint with `import/no-cycle` and `max-lines: 400`
- Use `tsc --noEmit` for type checking
- Component files should be focused and single-responsibility

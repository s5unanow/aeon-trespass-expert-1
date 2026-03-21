---
description: Schema contract direction enforcement — applies to packages/schemas/
globs: packages/schemas/**
---

- Contract direction: Python Pydantic -> JSON Schema -> TypeScript (never manual TS types)
- Run `make codegen` after any Pydantic model change to regenerate JSON Schema + TS types
- Never edit files in `packages/schemas/ts/` or `packages/schemas/jsonschema/` directly — they are generated

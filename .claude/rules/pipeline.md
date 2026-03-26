---
description: Python pipeline conventions — applies to apps/pipeline/ and packages/schemas/python/
globs: apps/pipeline/**,packages/schemas/python/**
---

- Use `ruff` for linting and formatting (McCabe complexity C901, max 12)
- `mypy --strict` — no type errors, no `Any` unless justified
- Use `structlog` for all logging — no `print()` or stdlib `logging`
- Use `pydantic` for all data models and validation
- Use `orjson` with atomic writes (temp file + rename) for JSON IO
- No bare `except Exception` without structured logging
- Max 400 lines per source file (enforced by `check_file_length.py`)
- Import layers enforced by `lint-imports` — no cyclic dependencies
- When concatenating text from a sequence containing mixed inline types (TextInline, IconInline, etc.), non-text inlines represent word boundaries — use `" "` as separator for skipped elements, never `"".join()` on the filtered subset alone

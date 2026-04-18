---
description: Python pipeline conventions — applies to apps/pipeline/ and packages/schemas/python/
globs: apps/pipeline/**,packages/schemas/python/**
---

- Use `ruff` for linting and formatting (McCabe complexity C901, max 12)
- `mypy --strict` — no type errors, no `Any` unless justified
- Logging: stdlib `logging.getLogger(__name__)` is the current default across the pipeline (18+ modules as of 2026-04-18; see `.claude/rules/AUDIT.md`). Prefer `structlog` for **new** services that need structured context fields; do not migrate existing stdlib-logging code just for the rule. Never use `print()` for diagnostic output in pipeline code.
- Use `pydantic` for all data models and validation
- JSON IO: stdlib `json` is current practice (`orjson` is not a project dependency). When writing artifacts to disk, always use atomic writes via `atr_pipeline.store.atomic_write.atomic_write_bytes` / `atomic_write_text` (temp file + `os.replace`) — never plain `Path.write_text` / `write_bytes` for artifact outputs.
- No bare `except Exception` without logging the exception context
- Max 400 lines per source file (enforced by `check_file_length.py`)
- Import layers enforced by `lint-imports` — no cyclic dependencies
- When concatenating text from a sequence containing mixed inline types (TextInline, IconInline, etc.), non-text inlines represent word boundaries — use `" "` as separator for skipped elements, never `"".join()` on the filtered subset alone

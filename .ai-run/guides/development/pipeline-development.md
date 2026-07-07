# Pipeline Development Practices (apps/pipeline)

**Language**: Python 3.12 | **Data models**: Pydantic | **CLI**: Typer

---

## Logging

Use stdlib `logging.getLogger(__name__)` — this is the current default across 18+ pipeline modules under `apps/pipeline/src/atr_pipeline/` (`stages/extract_native/`, `stages/extract_layout/`, `stages/qa/`, `runner/`, `services/llm/`, `cli/commands/run.py`, etc.). `structlog` is preferred only for **new** services that need structured context fields; do not migrate existing stdlib-logging code just to match a stricter rule (`.claude/rules/pipeline.md`).

```python
# Pattern
logger = logging.getLogger(__name__)
```

**Never** use `print()` for diagnostic output in pipeline code.

---

## Error Handling

No bare `except Exception` without logging the exception context — pass `exc_info=True` and a descriptive message so the failure is diagnosable:

```python
# Source: apps/pipeline/src/atr_pipeline/stages/extract_native/stage.py:86-88
except Exception:
    ctx.logger.warning(
        "Evidence extraction failed for %s, continuing", page_id, exc_info=True
    )
```

| ✅ DO | ❌ DON'T |
|-------|----------|
| `except Exception:` + `logger.warning(..., exc_info=True)` | Bare `except Exception: pass` |
| Log the entity/page id that failed | Swallow the exception with no context |

---

## Data Models

Use Pydantic `BaseModel` for every artifact schema, defined in `packages/schemas/python/atr_schemas/` — never elsewhere:

```python
# Source: packages/schemas/python/atr_schemas/qa_summary_v1.py:17-26
class QASummaryV1(BaseModel):
    schema_version: str = Field(default="qa_summary.v1", pattern=r"^qa_summary\.v\d+$")
    document_id: str
    ...
```

After adding/changing a model, run `make codegen` (regenerates JSON Schema + TS types) and `make check-codegen` to verify freshness.

---

## Artifact Writes

Always write artifacts via `atomic_write_bytes` / `atomic_write_text` (`apps/pipeline/src/atr_pipeline/store/atomic_write.py:10`) — never plain `Path.write_text` / `write_bytes`. JSON IO uses stdlib `json` (current practice; `orjson` is not a dependency).

---

## Stage-Output Cache Invalidation (mandatory when a stage gains a new side effect)

When a stage's `run()` method adds a new artifact write, a new `atomic_write_*` call, or any other new observable side effect, the stage class's `version` field **must** be bumped in the same change, and a regression test must exercise the executor's cache-hit path asserting the new side effect survives a cache hit.

**Why**: the executor cache key (`apps/pipeline/src/atr_pipeline/runner/cache_keys.py:7-16`) includes `stage_v={stage_version}`; an unchanged version means a cached stage event short-circuits `run()` entirely, silently omitting the new side effect for every existing and future cache hit (concrete precedent: `qa_metrics.json` shipped with an unbumped version and was silently absent from cached runs until fixed). Full rule + test template: `.claude/rules/pipeline.md` § "Stage-output cache invalidation".

---

## Complexity & File-Length Limits

| Metric | Limit | Enforced by |
|--------|-------|-------------|
| McCabe complexity | 12 | `ruff` `C901` (`pyproject.toml:34-37`) |
| Function parameters | 7 | `ruff` `PLR0913` (`pyproject.toml:39`) |
| Branches per function | 12 | `ruff` `PLR0912` (`pyproject.toml:40`) |
| Statements per function | 50 | `ruff` `PLR0915` (`pyproject.toml:41`) |
| File length | 400 lines | `scripts/check_file_length.py` (pre-existing violators grandfathered in `KNOWN_VIOLATORS`, must not grow) |

---

## Type Checking

`mypy --strict` (`pyproject.toml:74-89`) — no type errors, no `Any` unless justified. Third-party libraries without stubs (`fitz`, `docling`, `cv2`, `paddleocr`, `openai`, `anthropic`, `google.genai`) are allowlisted via `ignore_missing_imports` overrides, not blanket-ignored project-wide.

---

## Quick Reference

| Need | Location |
|------|----------|
| Logger setup pattern | any `stages/*/stage.py` |
| Atomic write helpers | `apps/pipeline/src/atr_pipeline/store/atomic_write.py` |
| Canonical schemas | `packages/schemas/python/atr_schemas/` |
| Stage executor / cache keys | `apps/pipeline/src/atr_pipeline/runner/cache_keys.py` |
| Ruff/mypy config | `pyproject.toml` |
| File-length checker | `scripts/check_file_length.py` |

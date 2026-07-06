# Development Practices — apps/pipeline

**Project**: atr-pipeline | **Language**: Python 3.12 | **Framework**: pydantic + typer
**Linter**: ruff (`pyproject.toml:35-71`) | **Formatter**: `ruff format`
**Type Checker**: mypy `--strict` (`pyproject.toml:74-89`)

---

## Logging

Stdlib `logging.getLogger(__name__)` is the current default across 26+
modules — not `structlog` and not `print()` (`.claude/rules/pipeline.md`).
`structlog` has zero usages in `apps/pipeline/src`; `structlog` is reserved
for *new* services that need structured context fields, not a migration
target for existing code (`.claude/rules/AUDIT.md` § `pipeline.md`).

### Setup

```python
# Source: services/llm/fallback.py:11
logger = logging.getLogger(__name__)
```

`StageContext` also carries a `logger` attribute (default
`logging.getLogger("atr_pipeline")`) so stages can log via `ctx.logger`
instead of a module-level logger — see `runner/stage_context.py:24`.

### Usage pattern

```python
# Source: stages/ingest/stage.py:78, 95
ctx.logger.info("Fingerprinting %s", pdf_path.name)
ctx.logger.info("Rasterizing %s at %s DPI", page_id, dpis)
```

### Rules

- ✅ Lazy `%s` formatting (never f-strings) so unused log calls avoid the format cost.
- ✅ `exc_info=True` on any warning/error logged from inside an `except` block (see Error Handling below).
- ❌ Never `print()` for diagnostic output in pipeline code (`.claude/rules/pipeline.md`).

---

## Error Handling

**Rule**: no bare `except Exception` without logging the exception context
(`.claude/rules/pipeline.md`). This is enforced by convention/review, not a
linter rule — every `except Exception` in the pipeline source logs before
continuing or re-raising.

### Pattern — log-and-continue (soft fallback)

```python
# Source: stages/extract_layout/stage.py:143-150
try:
    primary = extract_layout_docling(native, img, dpi=dpi)
except Exception:
    ctx.logger.warning(
        "Primary layout extraction failed for %s, escalating to OCR",
        native.page_id,
        exc_info=True,
    )
```

### Pattern — log-and-retry (with the exception object)

```python
# Source: services/llm/fallback.py:101-110
except Exception as exc:
    last_exc = exc
    logger.warning(
        "%s attempt %d/%d failed: %s", label, attempt, attempts, exc, exc_info=True,
    )
```

**Rules:**
- ✅ Always pass `exc_info=True` (or log the caught exception object) so the traceback survives.
- ✅ Prefer catching the narrowest exception type available; `except Exception` is only acceptable at a genuine fallback/retry boundary (external adapter call, best-effort secondary extraction path), and only with logging.
- ❌ Never catch-and-ignore silently (`except Exception: pass`).

---

## Atomic Writes

Every artifact write to disk goes through
`atr_pipeline.store.atomic_write.atomic_write_bytes` / `atomic_write_text` —
never plain `Path.write_text`/`write_bytes` for pipeline outputs
(`.claude/rules/pipeline.md`).

```python
# Source: store/atomic_write.py:11-30
def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write to a temp file in the same dir, fsync, then os.replace()."""
```

The write loop handles short `os.write()` returns explicitly and `fsync`s
before the rename so a crash never exposes a truncated or zero-length file.
`ArtifactStore.put_json`/`put_bytes` are the only call sites pipeline code
should use to persist stage output — they wrap `atomic_write_text`/
`atomic_write_bytes` and make writes content-addressed and idempotent
(`store/artifact_store.py:45-120`).

---

## Stage-output cache invalidation (load-bearing, non-obvious)

**Rule**: when a stage's `run()` method gains a new artifact write
(`ctx.artifact_store.put_json`/`put_binary`), a new `atomic_write_*` call, a
new persisted record, or any other new observable side effect, the stage
class's `version` property **must** be bumped in the same PR, **and** a
regression test must exercise the executor's cache-hit path and assert the
new side effect survives it (`.claude/rules/pipeline.md` § "Stage-output
cache invalidation").

**Why it's load-bearing**: `runner/cache_keys.py:8-35` (`build_cache_key`)
folds `stage_v={stage.version}` into the cache key. `runner/executor.py:56-84`
looks up `find_cached_event` by that key *before* calling `stage.run()` — an
unchanged version means a prior run's cached event short-circuits execution
entirely, and the new side effect silently never happens for any pre-existing
run. This is exactly what happened in the S5U-597 → S5U-640 incident: a new
`qa_metrics.json` artifact shipped with the stage version unchanged, and
cached runs silently omitted it until a follow-up bumped the version.

### Real precedent in this codebase

```python
# Source: stages/ingest/stage.py:29-46 — version bumped 1.1 -> 1.2 (S5U-1221)
# when extra_cache_inputs() started folding the source-PDF content hash into
# the cache key; also bumped 1.0 -> 1.1 (S5U-730) when run() started emitting
# a new page_images.v1 artifact per page.
```

```python
# Source: stages/qa/stage.py:51-60 — version bump history 1.0 -> 1.11,
# each bump commented inline with the S5U issue and whether it corresponds
# to a new artifact write or a selection-behavior cache-correctness change.
# Full history: tests/unit/stages/qa/test_stage_version.py module docstring.
```

### Required test shape

```python
# Source: apps/pipeline/tests/unit/stages/ingest/test_stage_cache_page_images_s5u730.py:1-21
# test_version_bump_invalidates_prior_ingest_cache — forges a cached event
# under the *prior* version, then asserts execute_stage() does NOT serve it:
# the live stage still runs and the new artifact still gets written.
```

`apps/pipeline/tests/unit/stages/ingest/test_stage_cache_pdf_content.py` is
the sibling example for a stage's `extra_cache_inputs()` hook (three-input
discipline: stable-on-unchanged-bytes, changes-on-changed-bytes,
missing-file sentinel).

---

## Mixed inline-text concatenation

**Rule**: when concatenating text from a sequence containing mixed inline
node types (`TextInline`, `IconInline`, `LineBreakInline`, `XrefInline`,
etc.), non-text inlines represent word boundaries — use `" "` as the
separator for skipped elements, never `"".join()` on the filtered subset
alone (`.claude/rules/pipeline.md`). Concatenating filtered text runs with
`"".join()` silently glues two words together wherever an icon or line break
was skipped.

```python
# Source: stages/assistant/chunker.py:158-175
def _extract_text(blocks: list[Block]) -> str:
    for child in children:
        if isinstance(child, TextInline):
            block_parts.append(child.text)
        else:
            block_parts.append(" ")   # non-text inline = word boundary
    parts.append("".join(block_parts).strip())
return " ".join(p for p in parts if p)
```

`stages/translation/grouping.py:112` shows the equivalent pattern applied at
the "join surviving text runs" level: `" ".join(node.text for node in inline
if isinstance(node, TextInline))` — space-joining the filtered runs rather
than `"".join()`-ing them.

---

## Configuration & Environment

### Loading pattern

```python
# Source: config/loader.py:46-90 — load_document_config()
# 3-layer TOML merge: configs/base.toml -> configs/{env}.toml (optional)
# -> configs/documents/{document_id}.toml, then DocumentBuildConfig.model_validate()
```

Config is TOML on disk, validated into pydantic models
(`config/models.py`) — never manually parsed dicts passed downstream.

### Accessing config

Stages receive the already-validated model via `ctx.config`
(`runner/stage_context.py:20`, `DocumentBuildConfig`); no stage re-reads
TOML directly.

---

## Common Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `extra_cache_inputs(ctx) -> list[str]` | A stage reads external state (a file, not just `DocumentBuildConfig`) that must invalidate the cache when it changes | `stages/ingest/stage.py:48-70` (hashes the source PDF bytes) |
| Cross-provider option-leakage guard | Reject config combinations that would silently no-op (e.g. CLI options set on an API provider) before constructing an adapter | `services/llm/factory.py:37-86` |
| Content-addressed idempotent write | Any stage output persisted to the artifact store | `store/artifact_store.py:45-77` (`put_json` no-ops if the content hash already exists) |

---

## Don't Do

| ❌ Avoid | ✅ Instead | Why |
|----------|-----------|-----|
| `Path.write_text(...)` / `Path.write_bytes(...)` for artifact output | `atomic_write_text`/`atomic_write_bytes` or `ArtifactStore.put_json`/`put_bytes` | Prevents partial writes becoming visible on crash/interruption |
| `except Exception: pass` | `except Exception as exc: logger.warning(..., exc_info=True)` | Silent failures are invisible in production and in CI logs |
| Adding a stage artifact write without bumping `version` | Bump `stage.version` + add a cache-hit regression test in the same PR | Unversioned cache keys silently serve stale output on every cache hit (S5U-597→S5U-640) |
| `"".join(text_run for run in mixed_inline if isinstance(run, TextInline))` | `" ".join(...)` or explicit `" "` placeholders for skipped non-text inlines | Prevents words gluing together across a skipped icon/line-break |

---

## Quick Reference

| Need | Location |
|------|----------|
| Atomic write helpers | `store/atomic_write.py` |
| Logger access in a stage | `ctx.logger` (`runner/stage_context.py`) or `logging.getLogger(__name__)` |
| Cache key composition | `runner/cache_keys.py` |
| Config loader | `config/loader.py` |
| Hashing utilities | `utils/hashing.py` |

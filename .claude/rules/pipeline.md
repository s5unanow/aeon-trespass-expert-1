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
- **Stage-output cache invalidation (S5U-662)** — when a pipeline stage's `run()` method adds a new artifact write (`ctx.artifact_store.put_json(...)` / `put_binary(...)`), a new call to `atomic_write_bytes` / `atomic_write_text`, a new persisted record, or any other new observable side-effect of execution, the stage class's `version` field **MUST** be bumped in the same PR, **AND** a regression test must exercise the executor's cache-hit path and assert the new side-effect is preserved on cached runs. Rationale: the executor cache key (`runner/cache_keys.py::build_cache_key`) includes `stage_v={stage_version}`; with an unchanged version a cached stage event short-circuits `run()` entirely — the new side-effect is silently absent for every pre-existing run and every future cache hit. See the S5U-597 → S5U-640 retrospective: `qa_metrics.json` was added to `QAStage.run` in S5U-597 with `version = "1.0"` unchanged, and cached runs silently omitted the artifact until S5U-640 bumped the version. Worked example of the required test shape:
    ```python
    def test_cache_hit_preserves_new_side_effect(tmp_path: Path) -> None:
        """Stage event is cached from a prior run; subsequent executor invocation
        must still emit the new artifact added to run()."""
        executor = build_executor(tmp_path)
        executor.run_stage(qa_stage)  # miss: run() executes, artifact written
        assert (tmp_path / "qa_metrics.v1" / "document" / ...).exists()
        (tmp_path / "qa_metrics.v1" / "document" / ...).unlink()  # simulate artifact loss
        executor.run_stage(qa_stage)  # hit: run() short-circuits — but we assert the invariant
        # If version wasn't bumped when the artifact was added, this assert fails —
        # which is exactly the regression we're guarding against.
        assert (tmp_path / "qa_metrics.v1" / "document" / ...).exists()
    ```
    The essence: the test must reach the cache-hit branch and assert the artifact/record is present on disk regardless. Reviewer probe in `.claude/prompts/review.md` (check #23) warns on stage.py diffs that add `put_json` / `put_binary` / `atomic_write_*` without a visible `version = "x.y"` line change; severity is WARNING because benign refactors exist (net-zero relocation across stages) and the worker must justify in the PR body.

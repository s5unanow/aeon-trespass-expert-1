# 001 — Executor cache integrity: hash the source PDF into the ingest cache key; verify cached artifacts exist on disk

- **Priority:** P0 — silent-wrong-output class
- **Effort:** S
- **Fix risk:** LOW
- **Dependency:** none
- **Category:** correctness / pipeline caching
- **Planned-at commit:** `fc98b82`
- **Safety-gate scope:** NO (pipeline source only — ships via the normal worker flow, not /coordinator)

## Why this matters

The pipeline's stage executor (`apps/pipeline/src/atr_pipeline/runner/executor.py`) caches stage results in a SQLite registry (`var/registry.db`) keyed by `build_cache_key(stage, version, schema, config_hash, input_hashes)`. Two verified defects make the cache lie:

1. **A replaced source PDF is served entirely from cache.** `IngestStage` has no `extra_cache_inputs` hook, and its cache key contains only the config hash — the config holds the PDF *path*, not its bytes. `fingerprint_pdf` runs inside `run()`, i.e. only on a cache miss. Swap the PDF at the configured path and re-run: ingest cache-hits and returns the old `SourceManifestV1` (old sha256), and every downstream stage cache-hits in turn — the whole run silently reflects the previous PDF. Only the web export catches it much later via `verify_source_pdf_sha` (S5U-889); `atr run` itself never notices.
2. **A cache hit never verifies the cached artifact still exists on disk.** The registry (`var/registry.db`) and the artifact store (`artifacts/`, gitignored) can diverge — partial cleanup, `make clean` (which does `rm -rf artifacts/*` but leaves `var/` alone), fresh checkout with a copied DB. On divergence the stage permanently short-circuits `run()` and downstream stages fail with confusing "missing artifacts" errors; nothing self-heals without a manual stage-version bump. This matches the project's recurring cache-invalidation pain (S5U-597 → S5U-640 retrospective in `.claude/rules/pipeline.md`).

This directly protects the held RU-edition rerun (S5U-997), which relies on per-stage cache hits being trustworthy.

## Current state (verified at fc98b82)

`apps/pipeline/src/atr_pipeline/runner/executor.py:43-45` — the executor already supports per-stage extra cache inputs:

```python
    extra_inputs_fn = getattr(stage, "extra_cache_inputs", None)
    if callable(extra_inputs_fn):
        i_hashes.extend(extra_inputs_fn(ctx))
```

`apps/pipeline/src/atr_pipeline/runner/executor.py:56-83` — the cache-hit branch returns without checking the store:

```python
    cached_event = find_cached_event(ctx.registry_conn, cache_key=cache_key)
    if cached_event is not None:
        cached_ref_str = cached_event["artifact_ref"]
        ...
        return StageResult(
            stage_name=stage.name,
            cache_key=cache_key,
            cached=True,
            artifact_ref=_parse_artifact_ref(cached_ref_str) if cached_ref_str else None,
        )
```

`apps/pipeline/src/atr_pipeline/stages/ingest/stage.py` — `IngestStage` defines `name`, `scope`, `version` ("1.1") and `run()`, but **no** `extra_cache_inputs`. The PDF is fingerprinted only inside `run()` (line 48: `sha256, page_count = fingerprint_pdf(pdf_path)`).

Supporting API that already exists:
- `apps/pipeline/src/atr_pipeline/store/artifact_store.py:66` — `def has(self, ref: ArtifactRef) -> bool:`
- `apps/pipeline/src/atr_pipeline/stages/ingest/pdf_fingerprint.py` — `fingerprint_pdf(path) -> (sha256, page_count)`
- Stages with `extra_cache_inputs` precedents: `stages/render/stage.py` (~line 83) and `stages/publish/stage.py` (~line 74) — copy their shape.
- Existing test exemplars: `apps/pipeline/tests/unit/runner/test_executor.py`, `apps/pipeline/tests/unit/runner/test_cache_keys.py`, `apps/pipeline/tests/unit/stages/ingest/test_stage_cache_page_images_s5u730.py`.

## Repo conventions that bind this change

- `.claude/rules/pipeline.md` § "Stage-output cache invalidation (S5U-662)": a stage-version bump is REQUIRED when `run()` gains a new observable side-effect. This change adds no new artifact write, but changing ingest's cache-key composition warrants a version bump anyway (1.1 → 1.2) so the change is self-documenting and reviewer check #23 stays quiet — document the rationale in the version-property docstring like the existing 1.0→1.1 comment.
- `mypy --strict`; ruff (C901 max 12); max 400 lines/file; no bare `except Exception` without logging.
- New tests need a `Red-before confirmation:` line in the commit message or PR body citing a pre-fix SHA + failure excerpt (`.claude/rules/hooks.md` § "Three-input test discipline"). Cited SHAs must be reachable from the branch HEAD.
- Independent fresh-eyes review (CLAUDE.md step 6) before any PR.

## Scope

**In scope:**
- `apps/pipeline/src/atr_pipeline/runner/executor.py`
- `apps/pipeline/src/atr_pipeline/stages/ingest/stage.py`
- New/extended tests: `apps/pipeline/tests/unit/runner/test_executor.py`, `apps/pipeline/tests/unit/stages/ingest/` (new file, e.g. `test_stage_cache_pdf_content.py`)

**Explicitly out of scope:**
- Making other stage summaries content-bearing (`TranslationResult`, `StructureResult`, `ExtractLayoutResult` count-only summaries) — separate follow-up.
- The `--from <stage>` empty-`upstream_refs` aliasing in `cli/commands/run.py` — separate follow-up.
- `registry/events.py` schema changes, `store/artifact_store.py`, mtime-latest selection, anything under `scripts/`.

## Git workflow

1. File/pick a Linear issue (project ATE1, team S5U); mark In Progress.
2. `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-executor-cache-integrity`
3. Commits prefixed `S5U-XXX:`. The 9-gate pre-commit hook runs automatically.
4. **Do not push or open a PR unless the user instructs.**

## Ordered steps

### Step 1 — Red tests first (capture the bugs)

Add two failing tests:

(a) In `apps/pipeline/tests/unit/runner/test_executor.py`: build a minimal stage + context (follow the file's existing fixtures), run `execute_stage` once (miss → artifact written), **delete the artifact file from the store root**, run `execute_stage` again with identical inputs, and assert the second result has `cached=False` (i.e. `run()` re-executed) — currently it returns `cached=True` with a dangling ref.

(b) New `apps/pipeline/tests/unit/stages/ingest/test_stage_cache_pdf_content.py`: assert `IngestStage` exposes `extra_cache_inputs(ctx)` whose returned list changes when the PDF bytes at `ctx.config.source_pdf_path` change (write two tiny distinct PDFs into `tmp_path`, or two distinct byte files if `fingerprint_pdf` requires real PDFs — use the fixture PDFs referenced by `test_stage_cache_page_images_s5u730.py` as a template). Also assert the value is stable for unchanged bytes.

Verify (expected: both new tests FAIL):
```bash
uv run pytest apps/pipeline/tests/unit/runner/test_executor.py apps/pipeline/tests/unit/stages/ingest/test_stage_cache_pdf_content.py -q
```
Record the failing output + the commit SHA of this red state for the `Red-before confirmation:` line.

### Step 2 — Cache-hit existence check in the executor

In `executor.py`'s cache-hit branch (after `cached_event is not None`): parse the ref first; if the ref parses and `not ctx.artifact_store.has(ref)`, log a warning (`ctx.logger.warning("Cache hit for %s but artifact missing on disk (ref=%s); re-running stage", ...)`) and **fall through to the execute path** instead of returning the cached result. A ref that fails to parse (`_parse_artifact_ref` returns `None`) should also fall through with a warning — do not preserve the current behavior of returning `cached=True, artifact_ref=None`.

Verify:
```bash
uv run pytest apps/pipeline/tests/unit/runner/ -q          # all pass, incl. step-1a test
uv run mypy apps/pipeline/src packages/schemas/python       # clean
```

### Step 3 — `extra_cache_inputs` on IngestStage + version bump

In `stages/ingest/stage.py`:
- Add `def extra_cache_inputs(self, ctx: StageContext) -> list[str]:` returning `[f"pdf_sha256:{sha256}"]` where the sha comes from hashing the file at `ctx.config.source_pdf_path` (reuse `fingerprint_pdf` or, if its page-count parse is too heavy for key computation, a plain sha256 of the file bytes — check `atr_pipeline.utils.hashing` for an existing file-hash helper before writing one). If the PDF is missing, return a sentinel like `["pdf_sha256:missing"]` rather than raising — `run()` already raises `FileNotFoundError` with a clear message and should remain the authoritative failure point.
- Bump `version` `"1.1"` → `"1.2"` and extend the docstring comment explaining: cache key now includes the source-PDF content hash so a replaced PDF invalidates ingest and the downstream chain.

Verify:
```bash
uv run pytest apps/pipeline/tests/unit/stages/ingest/ apps/pipeline/tests/unit/runner/ -q   # all pass
```

### Step 4 — Full local gates

```bash
make lint && make typecheck && make test
```
Expected: all green. (Note: `uv run pytest` full suite takes a few minutes.)

### Step 5 — Review + ship per CLAUDE.md

Re-read `git diff main...HEAD` for task-created debt; run the independent fresh-eyes review (Path A if the `Agent` tool is available); then stop — push/PR only on user instruction.

## Test plan

- New executor test: cache-hit-with-missing-artifact re-executes (three-input discipline: happy = artifact present → cached; failure = artifact deleted → re-run; adversarial = unparseable `artifact_ref` string in the registry row → re-run, not `cached=True/ref=None`).
- New ingest test: `extra_cache_inputs` changes with PDF bytes, stable otherwise; missing PDF returns sentinel without raising.
- Existing suites must stay green: `tests/unit/runner/test_executor.py`, `test_cache_keys.py`, `tests/unit/stages/ingest/test_stage_cache_page_images_s5u730.py` (this one exercises the cache-hit path and must be checked for assumptions broken by the existence check — it simulates artifact loss, which now triggers re-run; **read it before step 2 and adjust expectations consciously, documenting why in the PR body**).

## Machine-checkable done criteria

- [ ] `grep -n "extra_cache_inputs" apps/pipeline/src/atr_pipeline/stages/ingest/stage.py` returns a match.
- [ ] `grep -n '"1.2"' apps/pipeline/src/atr_pipeline/stages/ingest/stage.py` returns a match (version bumped).
- [ ] `grep -n "has(" apps/pipeline/src/atr_pipeline/runner/executor.py` shows the store existence check in the cache-hit branch.
- [ ] `uv run pytest apps/pipeline/tests/unit/runner/ apps/pipeline/tests/unit/stages/ingest/ -q` → 0 failures.
- [ ] `make lint && make typecheck && make test` → all green.
- [ ] Commit message or PR body contains `Red-before confirmation:` with a reachable SHA + failure excerpt.

## STOP conditions

- STOP if `test_stage_cache_page_images_s5u730.py` (or any `test_stage_cache_*` file) asserts that a cache hit must return `cached=True` even when artifacts were deleted — that test encodes the S5U-662 invariant ("artifact present on cached runs") and your change flips *how* it's satisfied (re-run instead of dangling hit). Reconcile semantics with the rule text in `.claude/rules/pipeline.md` before proceeding; if the rule's worked example becomes untrue, the PR must update the rule file too (which makes the PR touch `.claude/rules/` — still not safety-gate scope per the pre-pr regex, but call it out in review).
- STOP if hashing the PDF in `extra_cache_inputs` adds noticeable latency on every invocation (the 36 MB ATO PDF sha256 should be well under 1s; if a profiling check shows worse, switch to (size, mtime ns, sha-of-first-and-last-1MB) only with explicit justification in the PR body).
- STOP if `execute_stage`'s signature or `StageResult` shape needs changing — that fans out to all stages and exceeds this plan's scope.

## Maintenance notes

- Future stages that read external files must add their own `extra_cache_inputs`; this plan establishes ingest as the precedent alongside render/publish.
- The deeper fix (content-bearing stage summaries so downstream keys see upstream content, not counts) is a planned follow-up — see plans/README.md "Findings considered and not planned".

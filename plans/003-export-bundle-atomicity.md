# 003 — Close the export atomic-swap holes: live `images/` written before validation; non-atomic `index.json`; unchecked `os.write` in `atomic_write_bytes`

- **Priority:** P1 — data integrity of the published web bundle
- **Effort:** S
- **Fix risk:** LOW
- **Dependency:** none
- **Category:** correctness / artifact integrity
- **Planned-at commit:** `fc98b82`
- **Safety-gate scope:** NO (`scripts/export_to_web.py`, `scripts/_export_images.py`, pipeline store code — none match the safety-gate regex in `.claude/hooks/pre-pr-check.sh:242`). **BUT** `scripts/export_to_web.py` is on the visual-verify path list (`.claude/rules/visual-verify.md` and `pre-pr-check.sh:501`) — visual verification of an exported page is required before PR.

## Why this matters

S5U-890 built a two-phase, fail-closed commit for `make export`: every edition is built in a staging dir and the live bundle is only mutated by an atomic swap **after the whole bundle is proven** (`scripts/_export_commit.py` module docstring states the contract: "nothing live is mutated until the whole bundle is proven"). Three verified gaps remain:

1. **Live `images/` is written in phase 1.5, before staging/validation.** `extract_images()` writes decoded PDF images directly into the live `doc_public / "images"` directory. A later phase-2 validation refusal (the exact scenario S5U-890 exists for) still leaves live `images/` updated — a partial mutation the contract says cannot happen.
2. **`documents/index.json` is written non-atomically.** A plain `Path.write_text` on the live index; a crash mid-write leaves a truncated `index.json` that the reader's `DocumentIndexPage` fails to parse (and, due to a separate bug, renders as "No documents found").
3. **`atomic_write_bytes` issues a single unchecked `os.write` and never fsyncs.** `write(2)` may write fewer bytes than requested (signal interruption; >INT_MAX buffers on macOS for huge rasters) — a short write would be renamed into place as a truncated-but-"committed" artifact, defeating the module's stated invariant ("partial writes never become visible").

## Current state (verified at fc98b82)

`scripts/_export_images.py` (inside `extract_images(doc_id, doc_public, ...)`):
```python
    img_dir = doc_public / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    ...
            (img_dir / fname).write_bytes(img.image_bytes)
```

`scripts/export_to_web.py` (main flow, ~line 327): `extract_images(...)` is called after `verify_source_pdf_sha(...)` but **before** `reset_staging(doc_public, editions, pid, staged_rasters_dir)` — i.e. before phase 2 staging begins.

`scripts/export_to_web.py:143-150`:
```python
def write_document_index(documents_root: Path) -> None:
    """Write /documents/index.json listing all exported documents and editions."""
    entries = _build_document_index(documents_root)
    (documents_root / "index.json").write_text(
        json.dumps({"documents": entries}, ensure_ascii=False, indent=2)
    )
```

`apps/pipeline/src/atr_pipeline/store/atomic_write.py:11-24`:
```python
def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write data atomically by writing to a temp file, then renaming."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp_path, path)
```

Relevant existing machinery:
- `scripts/_export_commit.py` — `reset_staging(...)`, `commit_staged(...)` (staging build + crash-safe swap with backup/rollback). Read its full API before coding; the swap list is derived from the editions/rasters staging dirs.
- `export_to_web.py` already imports from `atr_pipeline`, so `from atr_pipeline.store.atomic_write import atomic_write_text` is layer-legal for fix 2.
- Existing test files to extend: `apps/pipeline/tests/unit/test_export_to_web_two_phase.py`, `test_export_to_web_two_phase_regress.py`, `test_export_to_web_swap_failure.py`, `test_export_to_web_image_binding.py`, `test_export_to_web.py`. No test file currently exists for `store/atomic_write.py` (verify with `grep -rl atomic_write apps/pipeline/tests/` and create one if absent).

## Repo conventions that bind this change

- `.claude/rules/pipeline.md`: artifact outputs must use atomic writes (`atomic_write_bytes`/`atomic_write_text`) — fix 2 brings `index.json` into compliance with the repo's own rule.
- The plain `write_text` calls inside `_export_pages.py`/`_export_qa.py` are **sanctioned** (they write into staging dirs gated by the atomic swap) — do not "fix" those.
- `.claude/rules/visual-verify.md`: `scripts/export_to_web.py` changes require visual verification (dev server on `localhost:3001`, Playwright MCP screenshot of an affected page) before PR.
- New tests need `Red-before confirmation:` evidence; mypy --strict; max 400 lines/file (check `_export_images.py` and `export_to_web.py` current lengths before adding code; if near the cap, put new logic in `_export_commit.py` or a helper module).

## Scope

**In scope:**
- `scripts/_export_images.py` (stage image writes)
- `scripts/export_to_web.py` (call order, `write_document_index` atomicity)
- `scripts/_export_commit.py` (extend swap list with the staged images dir)
- `apps/pipeline/src/atr_pipeline/store/atomic_write.py` (short-write loop + fsync)
- Tests: `apps/pipeline/tests/unit/test_export_to_web_two_phase*.py`, new `apps/pipeline/tests/unit/store/test_atomic_write.py` (or wherever store unit tests live — check `find apps/pipeline/tests -path '*store*'`)

**Explicitly out of scope:**
- `scripts/export_assistant_to_web.py` (audit it for the same pattern and file a follow-up if affected, but don't change it here)
- Raster staging (already handled by `staged_rasters_dir`)
- Anything in `apps/web/`
- The `make export` Makefile recipe

## Git workflow

1. File a Linear issue (ATE1/S5U); mark In Progress.
2. `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-export-atomicity`
3. Commits prefixed `S5U-XXX:`. **Do not push or open a PR unless the user instructs.**

## Ordered steps

### Step 1 — Read the commit module, then write red tests

Read `scripts/_export_commit.py` end-to-end (staging dir naming, `commit_staged` swap list, rollback semantics). Then add failing tests:

(a) In `test_export_to_web_two_phase.py` (or a new sibling): simulate a phase-2 validation refusal after `extract_images` ran (use the existing two-phase test harness — these tests already simulate refusal paths) and assert the live `doc_public/images/` directory is **unchanged** (no new files). Today it fails: images land live.

(b) For `write_document_index`: assert no `*.tmp`-less plain write — simplest behavioral pin: monkeypatch/interrupt is overkill; instead assert the function routes through `atomic_write_text` (e.g. monkeypatch `atomic_write_text` in the module namespace and assert it was called, or structurally grep). Prefer the monkeypatch-call assertion.

(c) New `test_atomic_write.py`: short-write resilience — monkeypatch `os.write` to write at most N bytes per call and assert the final file contains all bytes (drives the loop fix); plus an interruption test asserting no `.tmp` litter remains after an exception.

Verify (expected FAIL):
```bash
uv run pytest apps/pipeline/tests/unit/test_export_to_web_two_phase.py apps/pipeline/tests/unit/store/test_atomic_write.py -q
```
Record red output + SHA for `Red-before confirmation:`.

### Step 2 — Stage the images directory

- In `_export_images.py::extract_images`, accept a target dir parameter (or compute a staged path) so images are written under a staging dir (e.g. `doc_public / f".stage-images-{pid}"`), mirroring `reset_staging`'s naming convention for editions/rasters.
- In `export_to_web.py`, move the `extract_images` call after `reset_staging` (or pass the staged dir created by it), and extend `commit_staged`'s swap list in `_export_commit.py` so `images/` swaps atomically with the editions — including backup/rollback parity so a failed swap restores the prior `images/`.
- Keep the returned `page_images` mapping's `src` URLs unchanged (`/documents/{doc_id}/images/{fname}`) — only the on-disk write location during the build changes.

Verify:
```bash
uv run pytest apps/pipeline/tests/unit/test_export_to_web_two_phase.py apps/pipeline/tests/unit/test_export_to_web_two_phase_regress.py apps/pipeline/tests/unit/test_export_to_web_swap_failure.py apps/pipeline/tests/unit/test_export_to_web_image_binding.py -q
```
Expected: all green, including the step-1a test.

### Step 3 — Atomic `index.json`

In `export_to_web.py::write_document_index`, replace the plain `write_text` with `atomic_write_text(documents_root / "index.json", json.dumps(...))` (import from `atr_pipeline.store.atomic_write`).

Verify: step-1b test green; `uv run pytest apps/pipeline/tests/unit/test_export_to_web.py -q` green.

### Step 4 — Harden `atomic_write_bytes`

Replace the single `os.write(fd, data)` with a full-write loop (or `with os.fdopen(fd, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())` — fdopen takes ownership of fd, simplifying the error path; restructure the `except BaseException` cleanup accordingly so fd is not double-closed). Then `os.replace` as before. Keep the function signature and module docstring invariant intact.

Verify:
```bash
uv run pytest apps/pipeline/tests/unit/store/ -q
uv run mypy apps/pipeline/src packages/schemas/python
```

### Step 5 — End-to-end + visual verification

```bash
make lint && make typecheck && make test
uv run python scripts/export_to_web.py --review-only   # if artifacts/ + var/registry.db present locally
```
Expected: export completes; `apps/web/public/documents/index.json` valid JSON; images present at the live path. Then per `.claude/rules/visual-verify.md`: dev server on `localhost:3001`, navigate to `http://localhost:3001/documents/ato_core_v1_1/{edition}/p0040` (a page with figures), screenshot to `tmp/`, confirm images render.

NOTE: if local `artifacts/` or the registry is missing/stale (export needs a resolved run), skip the live export and rely on the unit suites — but say so explicitly in the PR body. The HELD RU draft bundle on disk must not be clobbered: `--review-only` rebuilds it; check with the user/owner before running a full export if the RU bundle state matters (see HANDOFF.md at repo root).

### Step 6 — Review per CLAUDE.md step 6, then stop (no push/PR without instruction).

## Test plan

- Phase-2 refusal leaves live `images/` byte-identical (new).
- Swap failure rolls back `images/` along with editions (extend `test_export_to_web_swap_failure.py`).
- `write_document_index` routes through `atomic_write_text` (new).
- `atomic_write_bytes`: short-write loop completes full payload; exception leaves no `.tmp` litter; written file replaces target atomically (new).
- All existing export suites green (`test_export_to_web*.py` — 8 files).
- Red-before evidence for every new test function.

## Machine-checkable done criteria

- [ ] `grep -n "write_bytes" scripts/_export_images.py` shows writes only into a staged dir variable, not `doc_public / "images"` directly.
- [ ] `grep -n "atomic_write_text" scripts/export_to_web.py` → match inside `write_document_index`.
- [ ] `grep -n "os.fsync\|fdopen" apps/pipeline/src/atr_pipeline/store/atomic_write.py` → match.
- [ ] `uv run pytest apps/pipeline/tests/unit/ -q -k "export_to_web or atomic_write"` → 0 failures.
- [ ] `make lint && make typecheck && make test` → green.
- [ ] PR body contains `Red-before confirmation:` lines and (if run) the visual-verification screenshot reference; if the live export was skipped, the PR body says so.

## STOP conditions

- STOP if `commit_staged`'s swap list is structurally edition-keyed and cannot accommodate a document-level `images/` dir without redesign — surface the design question (e.g. swap `images/` in a separate guarded step with its own backup) instead of bolting it on.
- STOP if any consumer reads live `images/` *during* the export build (grep `_export_blocks.py`, `_export_pages.py` for `images/` path reads) — staging would break them; reconcile first.
- STOP if `os.fsync` measurably slows full-document exports (hundreds of rasters): keep the full-write loop unconditionally but make fsync opt-in via parameter defaulted to True only for registry/store writes, with justification in the PR body.
- STOP before running any command that touches the on-disk RU draft bundle if HANDOFF.md still marks it HELD.

## Maintenance notes

- After this lands, the S5U-890 contract ("nothing live until proven") is true for *all* bundle surfaces: editions, rasters, images, index. Future export surfaces must join the staged swap, not write live.
- Audit `scripts/export_assistant_to_web.py` for the same live-write pattern; file a follow-up issue if found.

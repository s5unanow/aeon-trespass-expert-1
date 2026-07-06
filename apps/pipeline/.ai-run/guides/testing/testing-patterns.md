# Testing Patterns — apps/pipeline

**Project**: atr-pipeline
**Framework**: pytest (config: `apps/pipeline/pyproject.toml:41-46`; root `pyproject.toml:134-140` sets `testpaths` for repo-root runs)
**Test Location**: `apps/pipeline/tests/`

Worker discipline rules in `.claude/rules/hooks.md` and the stage-cache rule in
`.claude/rules/pipeline.md` are authoritative; this guide summarizes them.

---

## Test Organization

```
apps/pipeline/tests/
├── unit/                 Mirrors the package: cli/, config/, eval/, registry/,
│   │                     runner/, services/, stages/, store/
│   ├── conftest.py       Shared module-loader fixtures for repo scripts
│   └── test_check_*.py   Unit tests for repo-root `scripts/check_*.py` guards
├── integration/          CLI + end-to-end pipeline runs (test_cli_run.py,
│                         test_walking_skeleton_pipeline.py, test_hooks.py)
├── contract/             Pydantic ↔ JSON Schema roundtrips
│                         (test_schema_roundtrip.py, test_icon_inline_roundtrip.py)
└── safety_gate_corpus/   TOML adversarial corpora (hook_bypass.toml, …) that
                          drive detector contract tests such as
                          unit/test_check_hook_bypass_corpus.py
```

### Naming Conventions

| Element | Pattern | Example |
|---------|---------|---------|
| Test files | `test_<subject>.py`, issue-pinned regressions get an `_s5uNNN` suffix | `apps/pipeline/tests/unit/stages/translation/test_stage_cache_hit_s5u734.py` |
| Test functions | `test_<behavior>` | `test_execute_stage_cache_hit` — `apps/pipeline/tests/unit/runner/test_executor.py:99` |
| Module-wide marker | `pytestmark = pytest.mark.slow` | `test_stage_cache_hit_s5u734.py:47` |

---

## Markers (`apps/pipeline/pyproject.toml:43-46`)

| Marker | Meaning | How it runs |
|--------|---------|-------------|
| `slow` | Full-pipeline-chain / genuinely slow tests | **Excluded** from the pre-commit fast subset (`-m "not slow"`, `.claude/hooks/pre-commit-check.sh:157`); CI runs the full suite |
| `codex_live` | Shells out to a real `codex` CLI | Double-gated opt-in: select with `-m codex_live` **and** set `ATR_CODEX_LIVE_SMOKE=1`; either alone skips (`apps/pipeline/tests/unit/services/llm/test_codex_cli_smoke.py:7-18`) |

## Running Tests

| Action | Command (repo root) |
|--------|---------|
| All tests (what CI runs) | `uv run pytest` |
| Fast pre-commit subset | `uv run pytest -x -q --timeout=60 -m "not slow"` |
| Single file | `uv run pytest apps/pipeline/tests/unit/runner/test_executor.py` |
| Single test | `uv run pytest apps/pipeline/tests/unit/runner/test_executor.py::test_execute_stage_cache_hit` |
| Codex live smoke (opt-in) | `ATR_CODEX_LIVE_SMOKE=1 uv run pytest -m codex_live` |
| Aggregate local gate | `make check` (lint + typecheck + test) |

Bare `pytest` fails in this repo — always `uv run pytest` (`.claude/rules/hooks.md`).

---

## Fixtures

`apps/pipeline/tests/unit/conftest.py` provides **module-loader fixtures** that
import repo-root guard scripts as fresh modules per test (scripts are not
installed packages, so `importlib.util.spec_from_file_location` is the pattern):

| Fixture | Provides | Location |
|---------|----------|----------|
| `cct_mod` | Fresh `scripts/check_coverage_table.py` module | `apps/pipeline/tests/unit/conftest.py:38` |
| `guard` | Fresh `scripts/check_threshold_changes.py` module | `apps/pipeline/tests/unit/conftest.py:100` |
| `scope` | Fresh `scripts/check_visual_gate_scope.py` module | `apps/pipeline/tests/unit/conftest.py:127` |
| `cct_stub_fetcher` | Deterministic Linear `fetch_issue` stub factory | `apps/pipeline/tests/unit/conftest.py:199` |

Pipeline-level tests build real infrastructure in `tmp_path` instead of mocking
it: a `StageContext` with a real `ArtifactStore` and SQLite registry — see
`_make_ctx` in `test_stage_cache_hit_s5u734.py:54-79`. External LLM calls are
stubbed by config, not patching: `config.translation.provider = "mock"`
(`test_stage_cache_hit_s5u734.py:56`).

---

## Red-Before Evidence Discipline (MANDATORY)

Authoritative: `.claude/rules/hooks.md` § "Three-input test discipline". Every
PR adding a `def test_...` must prove the test fails without the fix, via a
`Red-before confirmation:` line in the commit message or PR body citing one of:
a commit SHA showing the failure, a pasted local-run failure excerpt at
`<sha>^`, or the literal `N/A — no production code change` carve-out.

| Avoid | Prefer |
|---|---|
| Merging a new test never seen red | Cite `commit <sha> shows <test> failing with "<excerpt>"` |
| Citing a fabricated / unreachable SHA | SHA from `git log main..HEAD` — reviewers run `git cat-file -e` + `git merge-base --is-ancestor` and grade failures CRITICAL |
| Silent parametrize-row additions | Cite red-before for new-branch rows, or state "fixture/data extension on existing branch" |
| Pinning a red-before label to an unrelated SHA | Use the local-run excerpt form when the mutation was never committed |

---

## Cache-Hit Regression Test (required for stage side-effect changes)

Per `.claude/rules/pipeline.md` § "Stage-output cache invalidation" (S5U-662):
when a stage's `run()` gains a new artifact write or observable side-effect,
bump the stage `version` **and** add a test that reaches the executor's
cache-hit branch and asserts the side-effect survives a cached run.

Shape (real examples):
1. Run the stage twice via `execute_stage`; assert `result2.cached` —
   `apps/pipeline/tests/unit/runner/test_executor.py:99`.
2. Assert every artifact from run 1 is still on disk (identical bytes) after
   the cache-hit run — `test_stage_cache_hit_s5u734.py:95`
   (`test_translation_stage_cache_hit_preserves_artifacts`), render variant at
   `apps/pipeline/tests/unit/stages/render/test_stage_cache_hit.py:150`.
3. Dangling-ref self-heal is separately pinned:
   `test_cache_hit_with_missing_artifact_reexecutes` —
   `apps/pipeline/tests/unit/runner/test_executor.py:203`.

---

## Safety-Gate Corpus Pattern

Detector guards are tested against named TOML corpora, not inline literals:
each case in `apps/pipeline/tests/safety_gate_corpus/hook_bypass.toml` is
`block` / `allow` / `known_residual`, and a contract test
(`apps/pipeline/tests/unit/test_check_hook_bypass_corpus.py`) drives the real
`scan()` over every case. New reviewer-found bypasses are added as corpus
`block` cases, not one-off regexes (`.claude/rules/hooks.md` § "Machine
contract — corpus-backed detector").

---

## Writing New Tests — Checklist

1. Place the file mirroring the package path under `tests/unit/`, or in
   `integration/` / `contract/` per the table above.
2. Mark full-pipeline-chain tests `pytest.mark.slow` so the pre-commit fast
   subset stays under its time budget (`test_stage_cache_hit_s5u734.py:45-47`).
3. Build real `tmp_path` infrastructure (StageContext + ArtifactStore +
   registry) rather than mocking store/registry internals.
4. Record red-before evidence before opening the PR (section above).
5. If the diff touches a stage's `run()` side-effects, include the cache-hit
   regression test and version bump in the same PR.

## Quick Reference

| Need | Location |
|------|----------|
| Pytest config + markers | `apps/pipeline/pyproject.toml:41-46` |
| Shared fixtures | `apps/pipeline/tests/unit/conftest.py` |
| Cache-hit test exemplar | `apps/pipeline/tests/unit/stages/translation/test_stage_cache_hit_s5u734.py` |
| Safety-gate corpora | `apps/pipeline/tests/safety_gate_corpus/` |
| Red-before rule (authoritative) | `.claude/rules/hooks.md` § "Three-input test discipline" |

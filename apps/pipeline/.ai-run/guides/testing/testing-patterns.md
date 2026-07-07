# Testing Patterns — apps/pipeline

**Framework**: pytest (config at root `pyproject.toml:134`, markers at `pyproject.toml:137`)
**Test root**: `apps/pipeline/tests/`
**Type/lint gates around tests**: `make check` (lint + typecheck + test) — see CLAUDE.md

## Test Organization

```
apps/pipeline/tests/
├── unit/                 mirrors src layout: cli/ config/ eval/ registry/
│                         runner/ services/ stages/ store/ + guard-script tests
├── integration/          CLI + multi-stage runs (test_walking_skeleton_pipeline.py)
├── contract/             schema roundtrip/JSON-Schema conformance
│                         (contract/test_schema_roundtrip.py:1)
└── safety_gate_corpus/   TOML corpora driving guard-detector contract tests
                          (safety_gate_corpus/hook_bypass.toml)
```

Naming: `test_<module>.py`, issue-pinned regressions get a suffix
(`unit/stages/translation/test_stage_cache_hit_s5u734.py`). Shared fixtures live
in `unit/conftest.py` (e.g. the `cct_mod` module-loader fixture,
`unit/conftest.py:39`). Sample-document fixtures live in
`packages/fixtures/sample_documents/` with integrity checked by
`packages/fixtures/manifest.toml` + `scripts/validate_fixture_manifest.py`
(run via `make validate-fixtures`).

## Fast vs Slow Split

The pre-commit hook runs only the fast subset:
`uv run pytest -x -q --timeout=60 -m "not slow"`
(`.claude/hooks/pre-commit-check.sh:157`). CI runs the full suite including slow
tests, without the timeout.

| Mark `slow` when | Keep fast when |
|---|---|
| Test drives a multi-stage chain (ingest→…→render) — module-level `pytestmark = pytest.mark.slow`, `unit/stages/qa/test_stage.py:35` | Test exercises one function/class with in-memory or tmp_path state |
| Test approaches the 60 s per-test timeout | Test finishes in milliseconds — the hook's budget target is <60 s total |

A second opt-in marker, `codex_live` (root `pyproject.toml:137`), gates tests
that shell out to a real `codex` CLI behind `ATR_CODEX_LIVE_SMOKE=1`.

## Running Tests

| Action | Command |
|---|---|
| All (repo root) | `make test` or `uv run pytest` |
| Fast subset (what the commit hook runs) | `uv run pytest -x -q --timeout=60 -m "not slow"` |
| Single file | `uv run pytest apps/pipeline/tests/unit/runner/test_executor.py` |
| Single test | `uv run pytest <file> -k test_execute_stage_cache_hit` |

Always `uv run pytest` — bare `pytest` fails in this repo
(`.claude/rules/hooks.md`, toolchain-wrappers bullet).

## Red-Before Discipline

Every new test function needs red-before evidence (a pre-fix SHA or failure
excerpt) in the commit message or PR body, and parametrize-row additions have
their own burden-of-proof rules. Do not restate the contract — the
authoritative form, SHA-resolution tripwire, and carve-outs are in
`.claude/rules/hooks.md` § "Three-input test discipline". The same section's
three-input habit (happy / failure / adversarial) applies to any gating logic
you test.

## Cache-Hit Regression Pattern

When a stage's `run()` gains a new observable side-effect, the stage `version`
bump must ship with a test that reaches the executor's cache-hit path and
asserts the side-effect survives a cached run. The rule and worked example are
authoritative in `.claude/rules/pipeline.md` § "Stage-output cache invalidation
(S5U-662)"; real instances in this suite:

- Executor-level: `unit/runner/test_executor.py:99`
  (`test_execute_stage_cache_hit` — second run returns `cached=True`, same key).
- Stage-level replay: `unit/stages/translation/test_stage_cache_hit_s5u734.py:1`
  runs the stage twice via `execute_stage` and asserts every persisted artifact
  is byte-identical after the cache-hit run, using the shared helper
  `assert_cache_hit_replays_artifact` (`unit/stages/qa/test_stage_cache_hit.py:159`).

Reuse that helper rather than hand-rolling the two-run assertion.

## Fixtures and Test Doubles

| Pattern | When | Evidence |
|---|---|---|
| `tmp_path` + real `ArtifactStore`/registry | Unit tests of runner/store behavior — no filesystem mocking | `unit/runner/test_executor.py:99` |
| `MockTranslator` instead of patching LLM clients | Any test touching translation; set `config.translation.provider = "mock"` | `services/llm/mock_translator.py:21`; usage in `unit/stages/translation/test_stage_cache_hit_s5u734.py` |
| Module-loader fixture for `scripts/*.py` guard scripts | Guard scripts aren't importable packages; load via `importlib` fixture | `unit/conftest.py:39` |
| Curated sample PDFs over synthetic inline PDFs | Stage tests needing realistic pages | `packages/fixtures/sample_documents/` (walking_skeleton, multi_column, …) |

Preference: real collaborators on `tmp_path` over mocks. Stages are wired
through `StageContext`, so tests inject a real store + registry into the
context instead of monkeypatching internals.

## Corpus-Driven Guard Tests

Safety-gate detectors are tested against named TOML corpora with `block` /
`allow` / `known_residual` cases (`safety_gate_corpus/hook_bypass.toml`,
driven by `unit/test_check_hook_bypass_corpus.py`). New detector bypasses found
in review are added as corpus cases, not one-off regexes — see
`.claude/rules/hooks.md` § "Machine contract — corpus-backed detector" and
`.claude/rules/guards.md` for the required degenerate-input and
rename/wrapper/alias coverage.

## Writing a New Test — Checklist

1. Place it in the mirror path (`unit/stages/<stage>/test_<topic>.py`).
2. Fast by default; add `pytest.mark.slow` only for multi-stage chains, with a
   one-line reason comment (see `unit/stages/qa/test_stage.py:34`).
3. Record red-before evidence per `.claude/rules/hooks.md`.
4. If the change adds a stage side-effect: version bump + cache-hit test (above).
5. Run the fast subset before committing: it is exactly what the hook runs.

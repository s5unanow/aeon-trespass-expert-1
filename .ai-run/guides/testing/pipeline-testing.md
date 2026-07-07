# Pipeline Testing (apps/pipeline)

**Framework**: pytest (`apps/pipeline/pyproject.toml:36-40`) | **Timeout plugin**: pytest-timeout
**Test location**: `apps/pipeline/tests/` (`unit/`, `integration/`)

---

## Running Tests

| Action | Command |
|--------|---------|
| All pipeline tests | `uv run pytest` |
| Fast subset (pre-commit) | `uv run pytest -x -q --timeout=60 -m "not slow"` |
| Hook integration tests only | `uv run pytest apps/pipeline/tests/integration/test_hooks.py -v --timeout=10` |
| Single file | `uv run pytest apps/pipeline/tests/unit/stages/qa/test_stage.py` |
| Full suite incl. slow (CI) | `uv run pytest --tb=short` |

---

## Test Markers

Declared in `apps/pipeline/pyproject.toml:38-40`:

| Marker | Meaning |
|--------|---------|
| `slow` | Skipped by the pre-commit fast subset (`-m "not slow"`); still runs in full CI |
| `codex_live` | Shells out to a real `codex` CLI; opt-in only via `ATR_CODEX_LIVE_SMOKE=1` |

---

## Stage Cache-Invalidation Test (required pattern)

Any change that adds a new artifact write inside a stage's `run()` must bump that stage's `version` field **and** add a regression test that exercises the executor's cache-hit path, asserting the new artifact survives a cached (short-circuited) run. Full rule and worked example: `.claude/rules/pipeline.md` § "Stage-output cache invalidation (S5U-662)". This is enforced by reviewer check #23 in `.claude/prompts/review.md`, not by CI.

---

## Red-Before Discipline (every new test)

Every new `def test_...` function must be verified to fail without its paired fix, and the PR/commit message must cite one of:

```
Red-before confirmation:
  - commit <sha> shows <test_name> failing with "<assertion excerpt>"
  - ran locally at <sha>^ (fix reverted); output: "<short excerpt>"
  - N/A — no production code change in this PR
```

Full discipline, SHA-resolution tripwire, and parametrize-row carve-outs: `.claude/rules/hooks.md` § "Three-input test discipline".

---

## Fixtures

Extraction-domain fixtures are mandatory for every extraction change (golden pages, roundtrip fixtures) — see `.ai-run/guides/workflows/pipeline-workflow.md` and `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` § 2. Fixture manifest integrity is checked by `uv run python scripts/validate_fixture_manifest.py` (`make validate-fixtures`).

---

## Quick Reference

| Need | Location |
|------|----------|
| Test config | `apps/pipeline/pyproject.toml:36-40` (`[tool.pytest.ini_options]`) |
| Unit tests | `apps/pipeline/tests/unit/` |
| Integration tests | `apps/pipeline/tests/integration/` |
| Stage cache-invalidation rule | `.claude/rules/pipeline.md` |
| Red-before test discipline | `.claude/rules/hooks.md` |

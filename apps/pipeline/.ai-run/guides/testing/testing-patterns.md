# Testing Patterns — apps/pipeline

**Project**: atr-pipeline | **Framework**: pytest (`pyproject.toml:134-140`)
**Test Location**: `apps/pipeline/tests/`

---

## Test Organization

```
apps/pipeline/tests/
├── unit/                 Mirrors src/atr_pipeline/ structure
│   ├── stages/<name>/    Per-stage unit tests (ingest, qa, structure, translation, …)
│   ├── services/llm/     Adapter tests (mocked external modules)
│   ├── runner/            executor/plan/cache_keys tests
│   ├── store/ registry/ config/ eval/ cli/
│   └── conftest.py        Module-loader fixtures for scripts/check_*.py (CI guards)
├── integration/           Full CLI pipeline runs via Typer CliRunner
├── contract/              Schema roundtrip + JSON Schema conformance
└── safety_gate_corpus/    TOML adversarial corpora consumed by CI-guard unit tests
```

`apps/pipeline/tests/unit/conftest.py` fixtures (`cct_mod`, `mod`, `guard`,
`scope`, `overrides_mod`, `corpus_cov`) are module-loader fixtures for the
repo's `scripts/check_*.py` CI guards, not pipeline domain fixtures — they
import a guard script as a fresh module per test (`tests/unit/conftest.py:22-35`).

### Naming Conventions

| Element | Pattern | Example |
|---------|---------|---------|
| Test files | `test_<module_or_feature>.py` | `test_stage_cache_page_images_s5u730.py` |
| Test functions | `test_<behavior>` | `test_version_bump_invalidates_prior_ingest_cache` |

---

## Running Tests

| Action | Command |
|--------|---------|
| All tests | `uv run pytest` (`Makefile:32`) |
| Fast subset (pre-commit) | `uv run pytest -x -q --timeout=60 -m "not slow"` (`.claude/hooks/pre-commit-check.sh:157`) |
| Hook integration tests | `make test-hooks` → `uv run pytest apps/pipeline/tests/integration/test_hooks.py -v --timeout=10` |
| Single file | `uv run pytest apps/pipeline/tests/unit/stages/ingest/test_stage.py` |
| Single test | `uv run pytest apps/pipeline/tests/unit/stages/ingest/test_stage.py::test_name` |

CI additionally runs the full suite (`pytest --tb=short`, includes `slow`
tests, no timeout) — the pre-commit fast subset is a local-only optimization.

---

## Markers

Declared in `pyproject.toml:137-140`:

| Marker | Meaning |
|--------|---------|
| `slow` | Skipped by the pre-commit fast subset (`-m "not slow"`); still runs in full CI |
| `codex_live` | Shells out to a real `codex` CLI; opt-in only via `ATR_CODEX_LIVE_SMOKE=1` (`apps/pipeline/tests/unit/services/llm/test_codex_cli_smoke.py`) |

---

## Unit Test Pattern — stage cache-invalidation

The most load-bearing unit-test shape in this module: proving a stage's
`version` bump actually invalidates a stale cached event.

```python
# Source: apps/pipeline/tests/unit/stages/ingest/test_stage_cache_page_images_s5u730.py:1-21
# Docstring states the invariant under test: a forged cached event written
# under IngestStage's PRIOR version must not short-circuit execute_stage();
# the live (bumped) version still runs and the new artifact still emits.
```

### Structure (three-input discipline)

```python
# Source: apps/pipeline/tests/unit/stages/ingest/test_stage_cache_pdf_content.py:65-97
def test_extra_cache_inputs_changes_with_pdf_bytes(tmp_path): ...   # happy: stable + changes
def test_extra_cache_inputs_missing_pdf_returns_sentinel(tmp_path): ...  # adversarial: missing file
```

Every new `def test_` added to this module must be verified red-before-fix
(`.claude/rules/hooks.md` § "Three-input test discipline") — the PR body or
commit message needs a `Red-before confirmation:` line citing a pre-fix SHA
or failure excerpt.

---

## Fixtures / Test Data

Extraction fixtures are mandatory for every extraction change
(`.claude/rules/extraction.md`) and live outside `apps/pipeline/tests/`:

```
packages/fixtures/manifest.toml                     # FixtureManifestEntry per fixture
packages/fixtures/sample_documents/<document_id>/
  source/          # input PDFs/PNGs
  expected/        # golden artifacts (JSON)
  catalogs/        # symbol catalogs (TOML)
  patches/         # source/target patches
```

Loaded via `atr_pipeline.eval.fixture_manifest` (`eval/fixture_manifest.py:16-17`,
`FIXTURES_DIR`/`MANIFEST_PATH` constants) and validated by
`scripts/validate_fixture_manifest.py` (`make validate-fixtures`, wired into
`make lint`).

### Golden refresh governance

Golden fixtures under `expected/` are governance-controlled
(`docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md:106-119`): never overwritten
silently, always a separate commit prefixed `S5U-XXX: refresh goldens`, with
an explicit before/after metric delta, never mixed with implementation
commits.

---

## Mocking

External LLM SDKs are mocked at the module level so adapter unit tests don't
require the real `openai`/`anthropic`/`google.genai` packages:

```python
# Source: apps/pipeline/tests/unit/services/llm/test_adapters.py:13-44
from unittest.mock import MagicMock, patch

def _mock_openai_module() -> tuple[ModuleType, MagicMock]:
    ...
    mock_cls = MagicMock()
```

| Layer | Mock In Unit Tests |
|-------|--------------------|
| LLM provider SDKs (openai/anthropic/google.genai) | ✅ Always — module-level `MagicMock`, see `test_adapters.py` |
| `codex`/`gemini`/`agy` CLI subprocess calls | ✅ Always, except the opt-in `codex_live`-marked smoke test |
| Registry (SQLite) / artifact store | ❌ Not mocked — tests use a real `tmp_path`-backed `ArtifactStore` + `open_registry()` (see cache-invalidation tests above) |

---

## Contract Testing — schema roundtrip

```python
# Source: apps/pipeline/tests/contract/test_schema_roundtrip.py:35-41
def _roundtrip(model_instance: object) -> None:
    """Serialize to JSON and deserialize back, assert equality."""
    model_cls = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
```

Exercises every core v1 schema (`PageIRV1`, `RenderPageV1`, `QARecordV1`,
`SourceManifestV1`, …) — guards the Pydantic → JSON Schema → TS codegen
contract from the schema side.

---

## Integration / CLI Testing

```python
# Source: apps/pipeline/tests/integration/test_cli_run.py:1-16
from typer.testing import CliRunner
from atr_pipeline.cli.main import app
# Invokes `atr run --doc walking_skeleton` through CliRunner; verifies exit
# code, artifact output, and registry stage-event records.
```

`_EXPECTED_STAGES` (`test_cli_run.py:18-31`) pins the full walking-skeleton
stage set so a stage silently dropped from `runner/plan.py` fails this test.

---

## Writing New Tests

### Checklist

1. Unit test for a stage: `apps/pipeline/tests/unit/stages/<name>/test_<behavior>.py`.
2. Build a `StageContext` via `tmp_path`-backed `ArtifactStore` + `open_registry` + `start_run` (see `test_stage_cache_pdf_content.py:38-62` for the canonical helper shape).
3. If the change adds a new artifact write, also add the cache-hit regression test (see "Stage-output cache invalidation" pattern above) and bump the stage's `version`.
4. Run: `uv run pytest apps/pipeline/tests/unit/stages/<name>/test_<behavior>.py -v`.
5. Record red-before evidence per `.claude/rules/hooks.md`.

---

## Quick Reference

| Need | Location |
|------|----------|
| Pytest config / markers | `pyproject.toml:134-140` |
| Extraction fixtures | `packages/fixtures/sample_documents/`, `packages/fixtures/manifest.toml` |
| Fixture manifest loader | `eval/fixture_manifest.py` |
| Fixture validator | `scripts/validate_fixture_manifest.py` |
| Golden refresh rules | `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` § 4 |

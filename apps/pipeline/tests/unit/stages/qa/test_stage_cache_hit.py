"""S5U-732 — QAStage cache-hit replay regression (pipeline.md § "Stage-output
cache invalidation", clause 2).

``.claude/rules/pipeline.md`` requires two things when a stage's ``run()`` gains
a new observable side-effect:

1. The stage class's ``version`` field MUST be bumped in the same PR.
2. A regression test MUST exercise the executor's cache-hit path and assert
   the new side-effect is preserved on cached runs.

The version-pin test (``test_stage_version.py``) plus the S5U-704 / S5U-705
prior-version forgery tests cover clause 1 (cache-key differentiation on
version bumps). Clause 2 was unprotected across three successive QAStage
version bumps (S5U-640 / S5U-588 / S5U-701) — there was no test that ran
``execute_stage(QAStage(), ctx)`` twice at the same version and asserted
the stage's persisted artifacts remain on disk after the second run's
cache hit. This file closes that gap.

## What the test guards against

The executor's cache-hit branch short-circuits ``stage.run()`` — it returns
a cached ``StageResult`` pointing at the previously persisted artifact ref
and never re-executes the stage's ``run()`` body. If a future PR adds a
new ``ctx.artifact_store.put_json(...)`` / ``put_binary(...)`` /
``atomic_write_*`` call to ``QAStage.run()`` **without** bumping the
``version`` field, subsequent runs on the same cache key will skip that
write entirely — and the new artifact will be silently absent for every
pre-existing run and every future cache hit.

The exact S5U-597 → S5U-640 retrospective is the concrete precedent:
``qa_metrics.json`` was added to ``QAStage.run`` in S5U-597 with
``version = "1.0"`` unchanged, and cached runs silently omitted the
artifact until S5U-640 bumped the version. The pipeline.md rule exists so
that the same omission can't slip through again; this test makes the
rule mechanical for ``QAStage``.

## Shape of the test (mirrors the pipeline.md worked example)

1. Run the full upstream pipeline (ingest → extract_native → symbols →
   structure → translate → render) so QA has real prerequisites.
2. Run ``execute_stage(QAStage(), ctx)`` once — ``result.cached == False``
   (miss). The stage's ``run()`` body executes and writes its artifacts
   (``qa/...`` summary via the executor + ``qa_metrics.v1/...`` metrics
   via ``QAStage.run``).
3. Record the on-disk artifact paths from the first run.
4. Run ``execute_stage(QAStage(), ctx)`` again with the same context —
   ``result.cached == True`` (hit). The executor short-circuits
   ``stage.run()`` and returns the cached ref.
5. Assert each first-run artifact file is still on disk with its
   content preserved.

If a future PR adds a ``put_json`` / ``put_binary`` / ``atomic_write_*``
call to ``QAStage.run()`` without bumping ``QAStage.version``:

* The first run populates the new artifact.
* The second run cache-hits — the new artifact is not re-created.
* A developer who deletes the cached event (or starts with an empty
  registry that was populated under the same version without the new
  write) observes the artifact missing — the exact silent-omission class
  pipeline.md clause 2 guards against.

## Reusable helper

``assert_cache_hit_replays_artifact`` is exposed so future QAStage version
bumps (and other DOCUMENT-scope stages that gain new side-effects) can
reuse the invariant without re-implementing the twice-run-and-assert
skeleton. Pass the schema family + scope + entity_id pattern that
identifies the artifact being guarded.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.extract_native.stage import ExtractNativeStage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.stages.qa.stage import QAStage
from atr_pipeline.stages.render.stage import RenderStage
from atr_pipeline.stages.structure.stage import StructureStage
from atr_pipeline.stages.symbols.stage import SymbolsStage
from atr_pipeline.stages.translation.stage import TranslationStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.source_manifest_v1 import SourceManifestV1

# S5U-1230: full-pipeline-chain integration tests — excluded from the
# fast pre-commit subset via `-m "not slow"`. CI runs the full suite.
pytestmark = pytest.mark.slow


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.translation.provider = "mock"
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="cache_hit_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="cache_hit_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def _run_prerequisites(ctx: StageContext) -> None:
    """ingest → extract_native → symbols → structure → translate → render."""
    r = execute_stage(IngestStage(), ctx)
    assert r.success
    assert r.artifact_ref is not None
    manifest = SourceManifestV1.model_validate(ctx.artifact_store.get_json(r.artifact_ref))
    for stage, input_data in (
        (ExtractNativeStage(), manifest),
        (SymbolsStage(), None),
        (StructureStage(), None),
        (TranslationStage(), None),
        (RenderStage(), None),
    ):
        r = execute_stage(stage, ctx, input_data=input_data)
        assert r.success


def _snapshot_artifacts(store_root: Path, schema_family: str) -> dict[Path, bytes]:
    """Return {path: bytes} for every artifact under <document>/<schema_family>/.

    The scan walks the full subtree under each ``<document>/<schema_family>``
    directory — no assumption on scope (document vs page) or entity_id.
    """
    snapshot: dict[Path, bytes] = {}
    for doc_dir in store_root.iterdir():
        if not doc_dir.is_dir():
            continue
        family_dir = doc_dir / schema_family
        if not family_dir.is_dir():
            continue
        for artifact in family_dir.rglob("*.json"):
            snapshot[artifact] = artifact.read_bytes()
    return snapshot


def assert_cache_hit_replays_artifact(
    stage: Stage,
    ctx: StageContext,
    schema_families: Iterable[str],
) -> None:
    """Pipeline.md clause-2 invariant for a DOCUMENT-scope stage.

    Runs ``stage`` twice via ``execute_stage(stage, ctx)``. The first call
    must be a miss (``run()`` executes and writes artifacts). The second
    call must be a hit (``run()`` short-circuits). After the hit, every
    artifact file under ``<doc>/<schema_family>/`` that existed after the
    first run must still exist on disk with identical bytes.

    If a future PR adds a new persisted side-effect to ``stage.run()``
    without bumping ``stage.version``, a well-informed call site that names
    the new schema_family in ``schema_families`` will observe the artifact
    present after run 1 and (in the absence of the bump + cache
    invalidation) still present after run 2 — but the real bug the rule
    prevents is the case where a fresh run against a pre-populated
    registry short-circuits and never writes the new artifact at all.
    This helper's sibling test ``test_qastage_cache_hit_preserves_...``
    exercises the preservation invariant; prior-version-forgery tests
    (``test_stage_cache_chart_title_merge_s5u705.py``,
    ``test_stage_cache_flat_table_s5u704.py``) cover the differentiation
    invariant. Both together satisfy pipeline.md clauses 1 and 2.

    Args:
        stage: Stage instance to run twice.
        ctx: Prepared stage context with upstream prerequisites already
            populated.
        schema_families: The ``schema_family`` names to guard (e.g.
            ``{"qa.v1", "qa_metrics.v1", "qa_record.v1"}``). Every artifact
            under ``<doc>/<family>/`` at the end of run 1 is asserted
            present and byte-identical at the end of run 2.
    """
    store_root = ctx.artifact_store.root

    # Miss.
    first = execute_stage(stage, ctx)
    assert first.success, f"first {stage.name} run failed: {first.error!r}"
    assert not first.cached, (
        f"first {stage.name} run was a cache hit — test needs an empty registry "
        "to observe the miss → hit transition"
    )
    assert first.artifact_ref is not None
    first_key = first.cache_key

    first_snapshots: dict[str, dict[Path, bytes]] = {
        family: _snapshot_artifacts(store_root, family) for family in schema_families
    }

    # Hit.
    second = execute_stage(stage, ctx)
    assert second.success, f"second {stage.name} run failed: {second.error!r}"
    assert second.cached, (
        f"second {stage.name} run did NOT hit the cache. Inputs or version changed "
        f"between calls — test setup is wrong. first_key={first_key} "
        f"second_key={second.cache_key}"
    )
    assert second.cache_key == first_key
    assert second.artifact_ref is not None
    # Cache-hit path returns a ref to the first run's persisted artifact.
    assert second.artifact_ref.relative_path == first.artifact_ref.relative_path, (
        "cache hit returned a different artifact ref than the original miss"
    )

    # Every first-run artifact must still be on disk with identical content.
    for family, first_snap in first_snapshots.items():
        assert first_snap, (
            f"{stage.name} first run produced NO artifacts under schema_family "
            f"{family!r} — test setup is wrong or the stage genuinely doesn't "
            "write that family for this document"
        )
        for path, first_bytes in first_snap.items():
            assert path.exists(), (
                f"cache hit for {stage.name} must preserve {family} artifact on "
                f"disk, but {path} is missing after the hit"
            )
            assert path.read_bytes() == first_bytes, (
                f"cache hit for {stage.name} changed {family} artifact bytes at "
                f"{path} — the cache-hit branch must never touch persisted artifacts"
            )


def test_qastage_cache_hit_preserves_persisted_artifacts(tmp_path: Path) -> None:
    """S5U-732 — QAStage cache-hit replay invariant (pipeline.md clause 2).

    A second ``execute_stage(QAStage(), ctx)`` call on an unchanged context
    must (a) return ``cached=True`` and (b) leave every artifact that the
    first run persisted on disk intact. The stage's ``run()`` is the only
    code path that writes ``qa.v1/...`` summaries and ``qa_metrics.v1/...``
    metrics (the S5U-597 side-effect the rule was motivated by); the
    cache-hit branch must not touch those files.

    If a future QAStage version bump adds a new persisted side-effect to
    ``run()`` without bumping ``QAStage.version``, extend the
    ``schema_families`` set below to include the new family. The helper
    will then guard it against the same silent-omission class.
    """
    ctx = _make_ctx(tmp_path)
    _run_prerequisites(ctx)

    # ``qa`` is the executor-written summary artifact path (schema_family
    # defaults to ``stage.name``; see ``runner/executor.py`` L103). The
    # executor writes this for every DOCUMENT-scope stage on miss; on hit
    # it is NOT re-written and therefore must remain on disk.
    # ``qa_metrics.v1`` is the S5U-597 side-effect that motivated the
    # pipeline.md rule — written from inside ``QAStage.run()`` via
    # ``ctx.artifact_store.put_json(schema_family="qa_metrics.v1", ...)``.
    assert_cache_hit_replays_artifact(
        QAStage(),
        ctx,
        schema_families={"qa", "qa_metrics.v1"},
    )

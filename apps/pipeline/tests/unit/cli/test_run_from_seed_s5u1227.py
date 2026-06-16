"""S5U-1227 — ``--from`` seeds ``upstream_refs`` from on-disk upstream summaries.

When a run starts mid-pipeline (``atr run --from <stage>``), the stages before
``from_stage`` are not executed, so the pre-S5U-1227 CLI started with an empty
``upstream_refs`` list — aliasing the first executed stage's cache key across
whatever upstream content happened to be on disk. ``_seed_upstream_refs``
resolves the content hash of each skipped stage's latest on-disk summary
artifact (the filename stem of ``{doc}/{stage}/document/{doc}/{hash}.json``) and
seeds ``upstream_refs`` with them, reproducing the prefix a full run would have
accumulated by the time it reached ``from_stage``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from atr_pipeline.cli.commands.run import _seed_upstream_refs
from atr_pipeline.cli.main import app
from atr_pipeline.runner.plan import SOURCE_ONLY_STAGES
from atr_pipeline.runner.result import StageResult
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash

runner = CliRunner()

_MOD = "atr_pipeline.cli.commands.run"
_SKIPPED = (
    ("ingest", {"a": 1}),
    ("extract_native", {"b": 2}),
    ("extract_layout", {"c": 3}),
    ("symbols", {"d": 4}),
)


def _seed_store(tmp_path: Path) -> ArtifactStore:
    """A real ArtifactStore seeded with the DOCUMENT-scope summary artifacts of
    every stage upstream of ``structure`` in the source-only plan."""
    store = ArtifactStore(tmp_path / "artifacts")
    for fam, payload in _SKIPPED:
        store.put_json(
            document_id="walking_skeleton",
            schema_family=fam,
            scope="document",
            entity_id="walking_skeleton",
            data=payload,
        )
    return store


def _expected_seed() -> list[str]:
    return [content_hash(payload) for _, payload in _SKIPPED]


def _mock_config(tmp: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.artifact_root = tmp / "artifacts"
    cfg.repo_root = tmp
    cfg.pipeline.version = "0.1.0"
    cfg.model_dump.return_value = {"x": 1}
    return cfg


def _ok(name: str) -> StageResult:
    ref = ArtifactRef(
        document_id="d", schema_family=name, scope="document", entity_id="d", content_hash="abc123"
    )
    return StageResult(stage_name=name, cache_key="k", cached=False, artifact_ref=ref)


def _ok_with_hash(name: str, c_hash: str) -> StageResult:
    ref = ArtifactRef(
        document_id="d", schema_family=name, scope="document", entity_id="d", content_hash=c_hash
    )
    return StageResult(stage_name=name, cache_key="k", cached=False, artifact_ref=ref)


def test_seed_upstream_refs_resolves_skipped_stages_in_order(tmp_path: Path) -> None:
    """``--from structure`` seeds the content hashes of every skipped upstream
    stage in plan order.

    Red-before: ``_seed_upstream_refs`` does not exist; ``--from`` started with
    an empty ``upstream_refs`` list regardless of on-disk upstream content.
    """
    store = _seed_store(tmp_path)
    seeded = _seed_upstream_refs(
        store,
        document_id="walking_skeleton",
        resolved_stages=["structure", "render"],
        edition="en",
    )
    assert seeded == _expected_seed()


def test_seed_upstream_refs_empty_for_first_stage(tmp_path: Path) -> None:
    """``--from ingest`` (the plan's first stage) seeds nothing — identical to
    the pre-S5U-1227 behaviour, so a full run is unchanged.

    Red-before: N/A — pins the no-regression invariant for the first stage.
    Reviewer asked to cross-check the diff.
    """
    store = _seed_store(tmp_path)
    seeded = _seed_upstream_refs(
        store,
        document_id="walking_skeleton",
        resolved_stages=["ingest", "extract_native"],
        edition="en",
    )
    assert seeded == []


def test_seed_upstream_refs_skips_missing_artifact(tmp_path: Path) -> None:
    """A skipped stage whose summary artifact is absent is omitted (not
    fabricated) — the downstream stage then surfaces its own missing-input error
    instead of serving a silent stale hit.

    Red-before: ``_seed_upstream_refs`` does not exist.
    """
    store = ArtifactStore(tmp_path / "artifacts")
    store.put_json(
        document_id="walking_skeleton",
        schema_family="ingest",
        scope="document",
        entity_id="walking_skeleton",
        data={"a": 1},
    )
    seeded = _seed_upstream_refs(
        store,
        document_id="walking_skeleton",
        resolved_stages=["structure", "render"],
        edition="en",
    )
    assert seeded == [content_hash({"a": 1})]


def test_run_from_threads_seeded_refs_into_first_stage(tmp_path: Path) -> None:
    """``atr run --from structure`` threads the seeded upstream refs into the
    first executed stage's ``input_hashes`` (not an empty list).

    Red-before: the CLI passed ``input_hashes=[]`` to the first stage under
    ``--from`` regardless of on-disk upstream content.
    """
    cfg = _mock_config(tmp_path)
    store = _seed_store(tmp_path)
    captured: list[Any] = []
    result_iter = iter([_ok_with_hash("structure", "h_structure"), _ok("render")])

    def _capture_execute(*a: Any, **kw: Any) -> StageResult:
        captured.append(kw)
        return next(result_iter)

    with (
        patch(f"{_MOD}.load_document_config", return_value=cfg),
        patch(f"{_MOD}.open_registry"),
        patch(f"{_MOD}.ArtifactStore", return_value=store),
        patch(f"{_MOD}.start_run"),
        patch(f"{_MOD}.finish_run"),
        patch(f"{_MOD}.update_run_provenance"),
        patch(f"{_MOD}.git_head", return_value="abc123"),
        patch(f"{_MOD}.build_run_manifest", return_value={}),
        patch(f"{_MOD}.set_run_manifest_ref"),
        patch(f"{_MOD}.build_run_summary"),
        patch(f"{_MOD}.atomic_write_text"),
        patch(f"{_MOD}.attach_run_log_handler", return_value=MagicMock()),
        patch(f"{_MOD}.detach_run_log_handler"),
        patch(
            f"{_MOD}.build_stage_registry",
            return_value={n: MagicMock(name=n) for n in SOURCE_ONLY_STAGES},
        ),
        patch(f"{_MOD}.execute_stage", side_effect=_capture_execute),
        patch(f"{_MOD}.SourceManifestV1"),
    ):
        cli_result = runner.invoke(
            app,
            [
                "run",
                "--doc",
                "walking_skeleton",
                "--edition",
                "en",
                "--from",
                "structure",
                "--to",
                "render",
            ],
        )

    assert cli_result.exit_code == 0, cli_result.stdout
    # First executed stage (structure) receives the seeded upstream refs.
    assert captured[0]["input_hashes"] == _expected_seed()
    # Second stage appends structure's own ref onto the seed.
    assert captured[1]["input_hashes"] == [*_expected_seed(), "h_structure"]

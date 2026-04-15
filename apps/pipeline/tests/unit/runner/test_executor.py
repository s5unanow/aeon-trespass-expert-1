"""Tests for the stage executor."""

from pathlib import Path

from pydantic import BaseModel

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope


class DummyOutput(BaseModel):
    value: int = 42


class DummyStage:
    """A trivial stage for testing the executor."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> BaseModel:
        return DummyOutput(value=42)


class FailingStage:
    """A stage that always fails."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> BaseModel:
        msg = "Stage failed on purpose"
        raise RuntimeError(msg)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _make_ctx(tmp_path: Path) -> StageContext:
    """Create a test StageContext."""
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="test_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="test_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_execute_stage_success(tmp_path: Path) -> None:
    """A successful stage produces an artifact and records an event."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(DummyStage(), ctx)

    assert result.success
    assert not result.cached
    assert result.artifact_ref is not None
    assert ctx.artifact_store.has(result.artifact_ref)


def test_execute_stage_cache_hit(tmp_path: Path) -> None:
    """Running the same stage twice with same inputs hits cache."""
    ctx = _make_ctx(tmp_path)

    result1 = execute_stage(DummyStage(), ctx, input_hashes=["fixed_input"])
    result2 = execute_stage(DummyStage(), ctx, input_hashes=["fixed_input"])

    assert result1.success
    assert not result1.cached
    assert result2.success
    assert result2.cached
    assert result1.cache_key == result2.cache_key


def test_execute_stage_failure(tmp_path: Path) -> None:
    """A failing stage records the error."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(FailingStage(), ctx)

    assert not result.success
    assert result.error is not None
    assert "failed on purpose" in result.error
    assert not result.cached


def test_page_filter_changes_cache_key(tmp_path: Path) -> None:
    """Same stage with different page filters produces different cache keys."""
    ctx_no_filter = _make_ctx(tmp_path / "a")
    ctx_filtered = _make_ctx(tmp_path / "b")
    ctx_filtered.page_filter = frozenset(["p0015", "p0018"])

    result_no_filter = execute_stage(DummyStage(), ctx_no_filter, input_hashes=["fixed"])
    result_filtered = execute_stage(DummyStage(), ctx_filtered, input_hashes=["fixed"])

    assert result_no_filter.cache_key != result_filtered.cache_key


def test_different_input_hashes_miss_cache(tmp_path: Path) -> None:
    """Different upstream refs cause a cache miss."""
    ctx = _make_ctx(tmp_path)

    result1 = execute_stage(DummyStage(), ctx, input_hashes=["upstream_v1"])
    result2 = execute_stage(DummyStage(), ctx, input_hashes=["upstream_v2"])

    assert result1.cache_key != result2.cache_key
    assert not result1.cached
    assert not result2.cached


class StageWithExtraInputs:
    """A stage that contributes extra cache inputs via ``extra_cache_inputs``."""

    def __init__(self, extras: list[str]) -> None:
        self._extras = extras

    @property
    def name(self) -> str:
        return "with_extras"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def extra_cache_inputs(self, ctx: StageContext) -> list[str]:
        return list(self._extras)

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> BaseModel:
        return DummyOutput(value=1)


def test_extra_cache_inputs_change_key(tmp_path: Path) -> None:
    """Stages may contribute extra inputs that invalidate the cache key.

    Regression for S5U-583: the render stage reads concepts.toml outside
    DocumentBuildConfig, so edits to that file must still flow through
    into the cache key.
    """
    ctx = _make_ctx(tmp_path)

    result_v1 = execute_stage(
        StageWithExtraInputs(extras=["concepts:abc123"]),
        ctx,
        input_hashes=["fixed"],
    )
    result_v2 = execute_stage(
        StageWithExtraInputs(extras=["concepts:def456"]),
        ctx,
        input_hashes=["fixed"],
    )
    result_v1_again = execute_stage(
        StageWithExtraInputs(extras=["concepts:abc123"]),
        ctx,
        input_hashes=["fixed"],
    )

    assert result_v1.cache_key != result_v2.cache_key
    assert result_v1.cache_key == result_v1_again.cache_key
    assert result_v1_again.cached

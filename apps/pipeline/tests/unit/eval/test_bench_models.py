"""Tests for benchmark ladder Pydantic models and TOML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.eval.bench_loader import discover_benchmark_ladders, load_benchmark_ladder
from atr_pipeline.eval.bench_models import (
    BenchmarkLadderConfig,
    BenchmarkReport,
    CheckpointResult,
    CheckpointSpec,
)


class TestCheckpointSpec:
    def test_valid(self) -> None:
        spec = CheckpointSpec(order=1, name="baseline", golden_set="core")
        assert spec.order == 1

    def test_order_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            CheckpointSpec(order=0, name="bad", golden_set="core")


class TestBenchmarkLadderConfig:
    def test_round_trip(self) -> None:
        config = BenchmarkLadderConfig(
            name="test_ladder",
            checkpoints=[
                CheckpointSpec(order=2, name="b", golden_set="gs_b"),
                CheckpointSpec(order=1, name="a", golden_set="gs_a"),
            ],
        )
        data = config.model_dump(mode="json")
        restored = BenchmarkLadderConfig.model_validate(data)
        assert restored.name == "test_ladder"
        assert len(restored.checkpoints) == 2

    def test_empty_checkpoints(self) -> None:
        config = BenchmarkLadderConfig(name="empty")
        assert config.checkpoints == []


class TestBenchmarkReport:
    def test_defaults(self) -> None:
        report = BenchmarkReport(ladder_name="test", timestamp="2026-01-01T00:00:00Z")
        assert report.passed is True
        assert report.frontier_checkpoint is None
        assert report.regressions == []

    def test_serialization_round_trip(self) -> None:
        report = BenchmarkReport(
            ladder_name="test",
            timestamp="2026-01-01T00:00:00Z",
            checkpoints=[
                CheckpointResult(order=1, name="a", golden_set="core", passed=True),
                CheckpointResult(
                    order=2, name="b", golden_set="multi", passed=False, is_frontier=True
                ),
            ],
            frontier_checkpoint=2,
            highest_passing=1,
            passed=False,
        )
        data = report.model_dump(mode="json")
        restored = BenchmarkReport.model_validate(data)
        assert restored.frontier_checkpoint == 2
        assert not restored.passed


class TestLoader:
    def test_load_extraction_ladder(self) -> None:
        config = load_benchmark_ladder("extraction_ladder")
        assert config.name == "extraction_ladder"
        assert len(config.checkpoints) == 7
        assert config.checkpoints[0].order == 1
        assert config.checkpoints[0].golden_set == "core"
        assert config.checkpoints[-1].order == 7

    def test_checkpoints_sorted_by_order(self) -> None:
        config = load_benchmark_ladder("extraction_ladder")
        orders = [c.order for c in config.checkpoints]
        assert orders == sorted(orders)

    def test_nonexistent_ladder_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_benchmark_ladder("nonexistent", repo_root=tmp_path)

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            load_benchmark_ladder("../evil")

    def test_discover(self) -> None:
        names = discover_benchmark_ladders()
        assert "extraction_ladder" in names

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        names = discover_benchmark_ladders(repo_root=tmp_path)
        assert names == []

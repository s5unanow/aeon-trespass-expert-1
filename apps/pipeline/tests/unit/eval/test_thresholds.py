"""Tests for metric threshold loading and evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.eval.thresholds import (
    MetricThreshold,
    ThresholdConfig,
    check_thresholds,
    load_thresholds,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


class TestLoadThresholds:
    """Tests for loading threshold TOML config."""

    def test_load_from_repo(self) -> None:
        """Can load the real configs/qa/thresholds.toml."""
        config = load_thresholds(repo_root=_repo_root())
        assert config.version == 1
        assert len(config.metric_thresholds) > 0

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when config is missing."""
        with pytest.raises(FileNotFoundError):
            load_thresholds(repo_root=tmp_path)

    def test_load_validates_fields(self) -> None:
        """Real thresholds have valid min values and names."""
        config = load_thresholds(repo_root=_repo_root())
        for t in config.metric_thresholds:
            assert 0.0 <= t.min <= 1.0
            assert t.name
            assert isinstance(t.blocking, bool)

    def test_load_custom_toml(self, tmp_path: Path) -> None:
        """Can load a custom threshold TOML."""
        qa_dir = tmp_path / "configs" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "thresholds.toml").write_text(
            "version = 1\n\n"
            "[[metric_thresholds]]\n"
            'name = "test_metric"\n'
            "min = 0.5\n"
            "blocking = false\n"
            'description = "test"\n'
        )
        config = load_thresholds(repo_root=tmp_path)
        assert config.version == 1
        assert len(config.metric_thresholds) == 1
        assert config.metric_thresholds[0].name == "test_metric"
        assert config.metric_thresholds[0].min == 0.5
        assert config.metric_thresholds[0].blocking is False


class TestCheckThresholds:
    """Tests for checking aggregate metrics against thresholds."""

    def test_all_pass(self) -> None:
        """All thresholds pass when values exceed minimums."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(name="accuracy_pass_rate", min=0.95, blocking=True),
                MetricThreshold(name="coverage_mean", min=0.90, blocking=True),
            ]
        )
        aggregate = {"accuracy_pass_rate": 1.0, "coverage_mean": 0.95}
        results = check_thresholds(aggregate, config)
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_blocking_failure(self) -> None:
        """Blocking threshold fails when value is below minimum."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(name="accuracy_pass_rate", min=0.98, blocking=True),
            ]
        )
        aggregate = {"accuracy_pass_rate": 0.90}
        results = check_thresholds(aggregate, config)
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].blocking

    def test_non_blocking_failure(self) -> None:
        """Non-blocking threshold fails but does not block."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(name="soft_metric", min=0.98, blocking=False),
            ]
        )
        aggregate = {"soft_metric": 0.50}
        results = check_thresholds(aggregate, config)
        assert len(results) == 1
        assert not results[0].passed
        assert not results[0].blocking

    def test_missing_metric_fails(self) -> None:
        """Missing metric in aggregate results in failure."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(name="missing_metric", min=0.95, blocking=True),
            ]
        )
        results = check_thresholds({}, config)
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].value is None

    def test_exact_threshold_passes(self) -> None:
        """Value exactly at threshold passes (>=)."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(name="metric", min=0.95, blocking=True),
            ]
        )
        aggregate = {"metric": 0.95}
        results = check_thresholds(aggregate, config)
        assert results[0].passed

    def test_empty_config(self) -> None:
        """Empty threshold config returns no results."""
        config = ThresholdConfig()
        results = check_thresholds({"accuracy": 1.0}, config)
        assert results == []

    def test_result_includes_description(self) -> None:
        """ThresholdResult carries through description."""
        config = ThresholdConfig(
            metric_thresholds=[
                MetricThreshold(
                    name="metric", min=0.5, blocking=True, description="test description"
                ),
            ]
        )
        results = check_thresholds({"metric": 1.0}, config)
        assert results[0].description == "test description"

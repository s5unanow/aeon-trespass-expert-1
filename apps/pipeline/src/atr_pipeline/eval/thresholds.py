"""Metric threshold configuration: model, loader, and evaluation."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from atr_pipeline.config.loader import _find_repo_root

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_PATH = "configs/qa/thresholds.toml"


class MetricThreshold(BaseModel):
    """A single metric threshold definition."""

    name: str
    min: float = Field(ge=0.0, le=1.0)
    blocking: bool = True
    description: str = ""


class ThresholdConfig(BaseModel):
    """Versioned threshold configuration loaded from TOML."""

    version: int = 1
    metric_thresholds: list[MetricThreshold] = Field(default_factory=list)


class ThresholdResult(BaseModel):
    """Result of checking one metric against its threshold."""

    name: str
    value: float | None
    threshold_min: float
    passed: bool
    blocking: bool
    description: str = ""


def load_thresholds(*, repo_root: Path | None = None) -> ThresholdConfig:
    """Load threshold config from configs/qa/thresholds.toml."""
    root = repo_root or _find_repo_root()
    path = root / _DEFAULT_THRESHOLD_PATH
    if not path.exists():
        msg = f"Threshold config not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return ThresholdConfig.model_validate(data)


def check_thresholds(
    aggregate: dict[str, float],
    config: ThresholdConfig,
) -> list[ThresholdResult]:
    """Check aggregate metrics against threshold config.

    Returns a ThresholdResult for each configured threshold.
    """
    results: list[ThresholdResult] = []
    for threshold in config.metric_thresholds:
        value = aggregate.get(threshold.name)
        if value is None:
            logger.warning("threshold metric not found in aggregate: %s", threshold.name)
            results.append(
                ThresholdResult(
                    name=threshold.name,
                    value=None,
                    threshold_min=threshold.min,
                    passed=False,
                    blocking=threshold.blocking,
                    description=threshold.description,
                )
            )
            continue
        passed = value >= threshold.min
        results.append(
            ThresholdResult(
                name=threshold.name,
                value=value,
                threshold_min=threshold.min,
                passed=passed,
                blocking=threshold.blocking,
                description=threshold.description,
            )
        )
    return results

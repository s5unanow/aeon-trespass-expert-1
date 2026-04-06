"""Repo-wide complexity summary for the erosion report.

Computes aggregate metrics across all tracked Python source files at two
git refs and classifies the trend as IMPROVING / STABLE / DRIFTING.
"""

from __future__ import annotations

import statistics
import subprocess
from collections.abc import Callable, Sequence
from typing import Any, TypedDict


class RepoMetricsSnapshot(TypedDict):
    total_functions: int
    total_complexity: int
    mean_complexity: float
    p90_complexity: int
    total_lines: int
    functions_over_threshold: int


class RepoSummary(TypedDict):
    base: RepoMetricsSnapshot
    head: RepoMetricsSnapshot
    delta: RepoMetricsSnapshot
    trend: str  # "IMPROVING" | "STABLE" | "DRIFTING"


# -- Trend classification thresholds ------------------------------------------

_DRIFT_MEAN_DELTA = 0.1
_DRIFT_P90_DELTA = 2
_DRIFT_OVER_THRESHOLD_DELTA = 1


# -- Helpers -------------------------------------------------------------------


def list_python_files(ref: str, dirs: Sequence[str]) -> list[str]:
    """List all tracked ``.py`` files under *dirs* at *ref* via git ls-tree."""
    paths: list[str] = []
    for d in dirs:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", d],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.endswith(".py"):
                paths.append(stripped)
    return paths


def _compute_p90(values: list[int]) -> int:
    """Return 90th percentile, or 0 if fewer than 2 values."""
    if len(values) < 2:
        return values[0] if values else 0
    deciles = statistics.quantiles(values, n=10)
    return int(deciles[-1])  # 9th decile = p90


def compute_repo_snapshot(
    ref: str,
    dirs: Sequence[str],
    *,
    get_file: Callable[[str, str], str | None],
    analyze: Callable[[str], Any],
    complexity_threshold: int,
) -> RepoMetricsSnapshot:
    """Compute aggregate metrics for all Python files at *ref*."""
    all_complexities: list[int] = []
    total_lines = 0
    over_threshold = 0

    for path in list_python_files(ref, dirs):
        source = get_file(ref, path)
        if source is None:
            continue
        total_lines += len(source.splitlines())
        for m in analyze(source):
            c: int = m["complexity"]
            all_complexities.append(c)
            if c > complexity_threshold:
                over_threshold += 1

    n = len(all_complexities)
    return RepoMetricsSnapshot(
        total_functions=n,
        total_complexity=sum(all_complexities),
        mean_complexity=round(sum(all_complexities) / n, 1) if n else 0.0,
        p90_complexity=_compute_p90(all_complexities),
        total_lines=total_lines,
        functions_over_threshold=over_threshold,
    )


def _snapshot_delta(base: RepoMetricsSnapshot, head: RepoMetricsSnapshot) -> RepoMetricsSnapshot:
    """Compute head minus base for each metric."""
    return RepoMetricsSnapshot(
        total_functions=head["total_functions"] - base["total_functions"],
        total_complexity=head["total_complexity"] - base["total_complexity"],
        mean_complexity=round(head["mean_complexity"] - base["mean_complexity"], 1),
        p90_complexity=head["p90_complexity"] - base["p90_complexity"],
        total_lines=head["total_lines"] - base["total_lines"],
        functions_over_threshold=(
            head["functions_over_threshold"] - base["functions_over_threshold"]
        ),
    )


def classify_trend(base: RepoMetricsSnapshot, head: RepoMetricsSnapshot) -> str:
    """Classify the trend between *base* and *head* snapshots.

    Returns ``"IMPROVING"``, ``"STABLE"``, or ``"DRIFTING"``.
    """
    mean_delta = head["mean_complexity"] - base["mean_complexity"]
    p90_delta = head["p90_complexity"] - base["p90_complexity"]
    over_delta = head["functions_over_threshold"] - base["functions_over_threshold"]

    drifting = (
        mean_delta >= _DRIFT_MEAN_DELTA
        or p90_delta >= _DRIFT_P90_DELTA
        or over_delta >= _DRIFT_OVER_THRESHOLD_DELTA
    )
    improving = (
        (mean_delta < 0 or over_delta < 0)
        and mean_delta < _DRIFT_MEAN_DELTA
        and p90_delta < _DRIFT_P90_DELTA
        and over_delta < _DRIFT_OVER_THRESHOLD_DELTA
    )

    if drifting:
        return "DRIFTING"
    if improving:
        return "IMPROVING"
    return "STABLE"


def compute_repo_summary(
    base_ref: str,
    head_ref: str,
    dirs: Sequence[str],
    *,
    get_file: Callable[[str, str], str | None],
    analyze: Callable[[str], Any],
    complexity_threshold: int = 12,
) -> RepoSummary:
    """High-level entry point: compute snapshots, delta, and trend."""
    base = compute_repo_snapshot(
        base_ref,
        dirs,
        get_file=get_file,
        analyze=analyze,
        complexity_threshold=complexity_threshold,
    )
    head = compute_repo_snapshot(
        head_ref,
        dirs,
        get_file=get_file,
        analyze=analyze,
        complexity_threshold=complexity_threshold,
    )
    return RepoSummary(
        base=base,
        head=head,
        delta=_snapshot_delta(base, head),
        trend=classify_trend(base, head),
    )

"""Tests for scripts/_repo_summary.py."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"


@pytest.fixture()
def repo_summary(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import _repo_summary.py as a module."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("_repo_summary", SCRIPT_DIR / "_repo_summary.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_repo_summary"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_repo_summary", None)


# -- Helpers -------------------------------------------------------------------


def _snap(
    total_functions: int = 0,
    total_complexity: int = 0,
    mean_complexity: float = 0.0,
    p90_complexity: int = 0,
    total_lines: int = 0,
    functions_over_threshold: int = 0,
) -> dict[str, Any]:
    return {
        "total_functions": total_functions,
        "total_complexity": total_complexity,
        "mean_complexity": mean_complexity,
        "p90_complexity": p90_complexity,
        "total_lines": total_lines,
        "functions_over_threshold": functions_over_threshold,
    }


# -- P90 computation ----------------------------------------------------------


class TestComputeP90:
    def test_empty(self, repo_summary: ModuleType) -> None:
        assert repo_summary._compute_p90([]) == 0

    def test_single_value(self, repo_summary: ModuleType) -> None:
        assert repo_summary._compute_p90([5]) == 5

    def test_known_distribution(self, repo_summary: ModuleType) -> None:
        values = list(range(1, 11))  # 1..10
        p90 = repo_summary._compute_p90(values)
        assert p90 >= 9  # 90th percentile of 1-10

    def test_uniform(self, repo_summary: ModuleType) -> None:
        values = [3, 3, 3, 3, 3]
        assert repo_summary._compute_p90(values) == 3


# -- Trend classification -----------------------------------------------------


class TestClassifyTrend:
    def test_identical_stable(self, repo_summary: ModuleType) -> None:
        s = _snap(total_functions=100, mean_complexity=3.0, p90_complexity=8)
        assert repo_summary.classify_trend(s, s) == "STABLE"

    def test_mean_up_drifting(self, repo_summary: ModuleType) -> None:
        base = _snap(mean_complexity=3.0, p90_complexity=8)
        head = _snap(mean_complexity=3.1, p90_complexity=8)
        assert repo_summary.classify_trend(base, head) == "DRIFTING"

    def test_p90_up_drifting(self, repo_summary: ModuleType) -> None:
        base = _snap(mean_complexity=3.0, p90_complexity=8)
        head = _snap(mean_complexity=3.0, p90_complexity=10)
        assert repo_summary.classify_trend(base, head) == "DRIFTING"

    def test_over_threshold_up_drifting(self, repo_summary: ModuleType) -> None:
        base = _snap(functions_over_threshold=4)
        head = _snap(functions_over_threshold=5)
        assert repo_summary.classify_trend(base, head) == "DRIFTING"

    def test_mean_down_improving(self, repo_summary: ModuleType) -> None:
        base = _snap(mean_complexity=3.5, p90_complexity=8, functions_over_threshold=4)
        head = _snap(mean_complexity=3.2, p90_complexity=8, functions_over_threshold=4)
        assert repo_summary.classify_trend(base, head) == "IMPROVING"

    def test_threshold_count_down_improving(self, repo_summary: ModuleType) -> None:
        base = _snap(mean_complexity=3.0, p90_complexity=8, functions_over_threshold=5)
        head = _snap(mean_complexity=3.0, p90_complexity=8, functions_over_threshold=4)
        assert repo_summary.classify_trend(base, head) == "IMPROVING"

    def test_mixed_below_thresholds_stable(self, repo_summary: ModuleType) -> None:
        base = _snap(mean_complexity=3.0, p90_complexity=8, functions_over_threshold=4)
        head = _snap(mean_complexity=3.05, p90_complexity=9, functions_over_threshold=4)
        assert repo_summary.classify_trend(base, head) == "STABLE"


# -- Snapshot delta ------------------------------------------------------------


class TestSnapshotDelta:
    def test_delta_computation(self, repo_summary: ModuleType) -> None:
        base = _snap(total_functions=100, total_complexity=300, total_lines=5000)
        head = _snap(total_functions=105, total_complexity=320, total_lines=5200)
        delta = repo_summary._snapshot_delta(base, head)
        assert delta["total_functions"] == 5
        assert delta["total_complexity"] == 20
        assert delta["total_lines"] == 200


# -- Integration with mocked git ----------------------------------------------


class TestComputeRepoSummary:
    def test_end_to_end(self, repo_summary: ModuleType) -> None:
        files = {"ref_a": {"src/a.py": "def f():\n    return 1\n"}, "ref_b": {}}
        files["ref_b"] = dict(files["ref_a"])
        files["ref_b"]["src/b.py"] = "def g(x):\n    if x > 0:\n        return x\n    return -x\n"

        def fake_get_file(ref: str, path: str) -> str | None:
            return files.get(ref, {}).get(path)

        def fake_analyze(source: str) -> list[dict[str, Any]]:
            import ast as _ast

            results = []
            tree = _ast.parse(source)
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    results.append({"complexity": 1, "name": node.name})
            return results

        def fake_list(ref: str, dirs: Any) -> list[str]:
            return list(files.get(ref, {}).keys())

        original_list = repo_summary.list_python_files
        repo_summary.list_python_files = fake_list
        try:
            result = repo_summary.compute_repo_summary(
                "ref_a",
                "ref_b",
                ("src",),
                get_file=fake_get_file,
                analyze=fake_analyze,
                complexity_threshold=12,
            )
        finally:
            repo_summary.list_python_files = original_list

        assert result["base"]["total_functions"] == 1
        assert result["head"]["total_functions"] == 2
        assert result["delta"]["total_functions"] == 1
        assert result["trend"] == "STABLE"


class TestListPythonFiles:
    def test_filters_py_only(self, repo_summary: ModuleType) -> None:
        """Verifies list_python_files uses git ls-tree (integration test)."""
        paths = repo_summary.list_python_files("HEAD", ("scripts",))
        assert all(p.endswith(".py") for p in paths)
        assert len(paths) > 0

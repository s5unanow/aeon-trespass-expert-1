"""Tests for scripts/check_code_erosion.py code erosion report."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_code_erosion.py"


@pytest.fixture()
def erosion(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_code_erosion.py as a module."""
    spec = importlib.util.spec_from_file_location("check_code_erosion", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_code_erosion"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_code_erosion", None)


# -- AST analysis unit tests ---------------------------------------------------


class TestComplexity:
    def test_simple_function(self, erosion: ModuleType) -> None:
        src = "def f():\n    return 1\n"
        results = erosion.analyze_source(src)
        assert len(results) == 1
        assert results[0]["complexity"] == 1
        assert results[0]["branches"] == 0

    def test_if_elif(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f(x):
                if x > 0:
                    pass
                elif x < 0:
                    pass
                else:
                    pass
        """)
        results = erosion.analyze_source(src)
        # if (+1) + elif-if (+1) = 2 branches, complexity = 3
        assert results[0]["branches"] == 2
        assert results[0]["complexity"] == 3

    def test_for_while(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f(items):
                for x in items:
                    while x > 0:
                        x -= 1
        """)
        results = erosion.analyze_source(src)
        assert results[0]["branches"] == 2  # for + while
        assert results[0]["complexity"] == 3

    def test_boolean_ops(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f(a, b, c):
                if a and b or c:
                    pass
        """)
        results = erosion.analyze_source(src)
        # if (+1) + and (+1) + or (+1) = 3 branches
        assert results[0]["branches"] == 3
        assert results[0]["complexity"] == 4

    def test_comprehension_with_if(self, erosion: ModuleType) -> None:
        src = "def f(xs):\n    return [x for x in xs if x > 0]\n"
        results = erosion.analyze_source(src)
        # comprehension (+1) + if filter (+1) = 2
        assert results[0]["branches"] == 2

    def test_except_handler(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f():
                try:
                    pass
                except ValueError:
                    pass
                except TypeError:
                    pass
        """)
        results = erosion.analyze_source(src)
        assert results[0]["branches"] == 2  # two except handlers

    def test_async_function(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            async def f():
                async for x in g():
                    async with ctx():
                        pass
        """)
        results = erosion.analyze_source(src)
        assert results[0]["branches"] == 2  # async for + async with

    def test_syntax_error_returns_empty(self, erosion: ModuleType) -> None:
        assert erosion.analyze_source("def f(:\n") == []


class TestFunctionMetrics:
    def test_statement_count(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f():
                a = 1
                b = 2
                return a + b
        """)
        results = erosion.analyze_source(src)
        assert results[0]["statements"] == 4  # lines 1-4

    def test_argument_count(self, erosion: ModuleType) -> None:
        src = "def f(a, b, /, c, *args, d=1, **kwargs):\n    pass\n"
        results = erosion.analyze_source(src)
        # a,b (posonly=2) + c (args=1) + d (kwonly=1) + *args (1) + **kwargs (1) = 6
        assert results[0]["args"] == 6

    def test_multiple_functions(self, erosion: ModuleType) -> None:
        src = textwrap.dedent("""\
            def f():
                pass

            def g():
                if True:
                    pass
        """)
        results = erosion.analyze_source(src)
        assert len(results) == 2
        assert results[0]["name"] == "f"
        assert results[1]["name"] == "g"
        assert results[1]["complexity"] == 2


# -- Violations ----------------------------------------------------------------


class TestViolations:
    def test_over_threshold(self, erosion: ModuleType) -> None:
        m: dict[str, Any] = {
            "name": "f",
            "line": 1,
            "complexity": 15,
            "branches": 14,
            "statements": 60,
            "args": 3,
        }
        vs = erosion._violations_for(m)
        assert "C901" in vs
        assert "PLR0912" in vs
        assert "PLR0915" in vs
        assert "PLR0913" not in vs

    def test_under_threshold(self, erosion: ModuleType) -> None:
        m: dict[str, Any] = {
            "name": "f",
            "line": 1,
            "complexity": 5,
            "branches": 4,
            "statements": 10,
            "args": 2,
        }
        assert erosion._violations_for(m) == []


# -- Hotspot ratchet -----------------------------------------------------------


class TestHotspotRatchet:
    def _mock_file(self, content_map: dict[str, str | None]) -> Any:
        def fake_get(ref: str, path: str) -> str | None:
            return content_map.get(f"{ref}:{path}")

        return fake_get

    def test_worsened(self, erosion: ModuleType) -> None:
        base_src = "def f():\n    pass\n"
        head_src = "def f():\n    if True:\n        pass\n    if True:\n        pass\n"
        content: dict[str, str | None] = {}
        for path in erosion.HOTSPOT_REGISTRY:
            content[f"main:{path}"] = base_src
            content[f"HEAD:{path}"] = head_src
        with patch.object(erosion, "get_file_at_ref", side_effect=self._mock_file(content)):
            entries = erosion.compute_hotspot_ratchet("main", "HEAD")
        assert all(e["verdict"] == "WORSENED" for e in entries)

    def test_unchanged(self, erosion: ModuleType) -> None:
        src = "def f():\n    pass\n"
        content: dict[str, str | None] = {}
        for path in erosion.HOTSPOT_REGISTRY:
            content[f"main:{path}"] = src
            content[f"HEAD:{path}"] = src
        with patch.object(erosion, "get_file_at_ref", side_effect=self._mock_file(content)):
            entries = erosion.compute_hotspot_ratchet("main", "HEAD")
        assert all(e["verdict"] == "UNCHANGED" for e in entries)

    def test_improved(self, erosion: ModuleType) -> None:
        base_src = "def f():\n    if True:\n        pass\n    if True:\n        pass\n"
        head_src = "def f():\n    pass\n"
        content: dict[str, str | None] = {}
        for path in erosion.HOTSPOT_REGISTRY:
            content[f"main:{path}"] = base_src
            content[f"HEAD:{path}"] = head_src
        with patch.object(erosion, "get_file_at_ref", side_effect=self._mock_file(content)):
            entries = erosion.compute_hotspot_ratchet("main", "HEAD")
        assert all(e["verdict"] == "IMPROVED" for e in entries)

    def test_missing_on_base(self, erosion: ModuleType) -> None:
        head_src = "def f():\n    pass\n"
        content: dict[str, str | None] = {}
        for path in erosion.HOTSPOT_REGISTRY:
            content[f"main:{path}"] = None
            content[f"HEAD:{path}"] = head_src
        with patch.object(erosion, "get_file_at_ref", side_effect=self._mock_file(content)):
            entries = erosion.compute_hotspot_ratchet("main", "HEAD")
        assert all(e["verdict"] == "WORSENED" for e in entries)


# -- Report and CLI ------------------------------------------------------------


class TestReport:
    def test_json_keys(self, erosion: ModuleType) -> None:
        report = erosion.build_report("main", "HEAD", [], ([], 0), ([], 0, 0.0), [])
        assert set(report.keys()) == {
            "base",
            "head",
            "files_changed",
            "files_in_scope",
            "structural_erosion",
            "verbosity_drift",
            "hotspot_ratchet",
        }

    def test_always_exits_zero(self, erosion: ModuleType) -> None:
        with (
            patch.object(erosion, "get_changed_files", return_value=[]),
            patch.object(erosion, "get_file_at_ref", return_value=None),
        ):
            assert erosion.main(["--base", "main", "--head", "HEAD"]) == 0

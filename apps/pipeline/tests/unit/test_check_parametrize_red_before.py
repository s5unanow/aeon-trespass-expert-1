"""Tests for scripts/check_parametrize_red_before.py (S5U-650).

Three-input matrix per .claude/rules/hooks.md and G1 fail-closed
discipline per .claude/rules/guards.md:

  Happy path     — added row inside an existing parametrize block: flagged
  Failure path   — added line in a regular function body: not flagged
  Adversarial    — pytest_generate_tests body, @given widening, stacked
                   decorators, fixture without params= (not flagged),
                   class-level parametrize, vitest .ts skip

  G1a — missing base ref: SystemExit
  G1b — malformed Python at head: skipped with a warning, not silent pass
  G1c — empty diff: exit 0

Red-before confirmation: N/A — no production code change in this PR
(the helper is brand-new; these tests are its first observable
contract). Reviewer asked to cross-check that the AST-walk shape
matches the surfaces documented in tmp/plan-s5u-650.md §4b.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_parametrize_red_before.py"
_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


@pytest.fixture()
def helper(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_parametrize_red_before", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_parametrize_red_before"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_parametrize_red_before", None)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@e",
        "HOME": str(repo),
        "PATH": _PATH_ENV,
    }
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, env=env, capture_output=True, text=True
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "user.email", "t@e")
    (repo / "README.md").write_text("test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")


def _commit(repo: Path, rel: str, content: str, *, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _invoke(
    repo: Path, *, base: str = "HEAD~1", head: str = "HEAD"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--base", base, "--head", head, "--json"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


# -- AST-level unit tests via analyze_file --------------------------------


def test_unit_pytest_mark_parametrize_flagged(helper: ModuleType) -> None:
    """Happy: `@pytest.mark.parametrize(...)` is detected."""
    src = (
        "import pytest\n\n"
        "@pytest.mark.parametrize('a,b', [\n"
        "    (1, 2),\n"
        "    (3, 4),\n"
        "])\n"
        "def test_x(a, b): pass\n"
    )
    matches, skips = helper.analyze_file("t.py", src, [4, 5])
    assert skips == []
    labels = {(m.line, m.context, m.function) for m in matches}
    assert labels == {
        (4, "pytest.mark.parametrize", "test_x"),
        (5, "pytest.mark.parametrize", "test_x"),
    }


def test_unit_given_widening_flagged(helper: ModuleType) -> None:
    """Adversarial: `@given(...)` strategy widening is detected."""
    src = (
        "from hypothesis import given, strategies as st\n\n"
        "@given(st.one_of(\n"
        "    st.integers(),\n"
        "    st.text(),\n"
        "))\n"
        "def test_x(value): pass\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [4, 5])
    assert {(m.line, m.context) for m in matches} == {(4, "given"), (5, "given")}


def test_unit_fixture_with_params_flagged(helper: ModuleType) -> None:
    """Adversarial: `@pytest.fixture(..., params=[...])` is detected."""
    src = (
        "import pytest\n\n"
        "@pytest.fixture(params=[\n"
        "    'a',\n"
        "    'b',\n"
        "])\n"
        "def my_fixture(request): return request.param\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [4, 5])
    assert {m.line for m in matches} == {4, 5}
    assert all(m.context == "pytest.fixture(params=...)" for m in matches)


def test_unit_fixture_without_params_not_flagged(helper: ModuleType) -> None:
    """Adversarial: `@pytest.fixture` without `params=` kwarg is NOT a parametrize vector."""
    src = (
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def my_fixture():\n"
        "    cases = [\n"
        "        'a',\n"
        "        'b',\n"
        "    ]\n"
        "    return cases\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [6, 7])
    assert matches == []


def test_unit_pytest_generate_tests_body_flagged(helper: ModuleType) -> None:
    """Adversarial: lines inside `pytest_generate_tests` body are flagged."""
    src = (
        "def pytest_generate_tests(metafunc):\n"
        "    cases = [\n"
        "        ('a', 1),\n"
        "        ('b', 2),\n"
        "    ]\n"
        "    metafunc.parametrize('name,value', cases)\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [3, 4])
    assert {(m.line, m.context) for m in matches} == {
        (3, "pytest_generate_tests"),
        (4, "pytest_generate_tests"),
    }


def test_unit_stacked_parametrize_decorators(helper: ModuleType) -> None:
    """Adversarial: row added in second of two stacked decorators is flagged."""
    src = (
        "import pytest\n\n"
        "@pytest.mark.parametrize('a', [1, 2])\n"
        "@pytest.mark.parametrize('b', [\n"
        "    3,\n"
        "    4,\n"
        "])\n"
        "def test_x(a, b): pass\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [5, 6])
    assert all(m.context == "pytest.mark.parametrize" for m in matches)
    assert {m.line for m in matches} == {5, 6}


def test_unit_class_level_parametrize_flagged(helper: ModuleType) -> None:
    """Adversarial: row added inside class-level `@parametrize` is flagged."""
    src = (
        "import pytest\n\n"
        "@pytest.mark.parametrize('a,b', [\n"
        "    (1, 2),\n"
        "    (3, 4),\n"
        "])\n"
        "class TestFoo:\n"
        "    def test_x(self, a, b): pass\n"
    )
    matches, _ = helper.analyze_file("t.py", src, [4, 5])
    assert all(m.context == "pytest.mark.parametrize" for m in matches)
    assert {m.line for m in matches} == {4, 5}


def test_unit_plain_function_body_not_flagged(helper: ModuleType) -> None:
    """Failure: regular function body with no decorator is NOT flagged."""
    src = "def test_foo():\n    x = [\n        1,\n        2,\n    ]\n    assert x == [1, 2]\n"
    matches, _ = helper.analyze_file("t.py", src, [3, 4])
    assert matches == []


def test_unit_malformed_python_returns_skip(helper: ModuleType) -> None:
    """G1b: malformed Python at head returns Skip, does not raise."""
    src = "def broken(:\n    pass\n"
    matches, skips = helper.analyze_file("t.py", src, [1, 2])
    assert matches == []
    assert len(skips) == 1
    assert "syntax error" in skips[0].reason.lower()


# -- End-to-end script invocation tests -----------------------------------


def test_e2e_happy_parametrize_row_addition_exit_1(tmp_path: Path) -> None:
    """Happy: parametrize row addition → exit 1, JSON lists rows."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(
        repo,
        "tests/test_x.py",
        (
            "import pytest\n\n"
            "@pytest.mark.parametrize('a,b', [\n"
            "    (1, 2),\n"
            "])\n"
            "def test_x(a, b): pass\n"
        ),
        msg="initial",
    )
    _commit(
        repo,
        "tests/test_x.py",
        (
            "import pytest\n\n"
            "@pytest.mark.parametrize('a,b', [\n"
            "    (1, 2),\n"
            "    (3, 4),\n"
            "    (5, 6),\n"
            "])\n"
            "def test_x(a, b): pass\n"
        ),
        msg="add rows",
    )
    proc = _invoke(repo)
    assert proc.returncode == 1, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["matches"], data
    assert all(m["context"] == "pytest.mark.parametrize" for m in data["matches"])


def test_e2e_failure_plain_function_exit_0(tmp_path: Path) -> None:
    """Failure: rows added in plain function body → exit 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(
        repo,
        "tests/test_y.py",
        "def test_foo():\n    cases = [1]\n    assert cases == [1]\n",
        msg="initial",
    )
    _commit(
        repo,
        "tests/test_y.py",
        (
            "def test_foo():\n"
            "    cases = [\n"
            "        1,\n"
            "        2,\n"
            "    ]\n"
            "    assert cases == [1, 2]\n"
        ),
        msg="extend list",
    )
    proc = _invoke(repo)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_e2e_g1a_missing_base_ref_fails_closed(tmp_path: Path) -> None:
    """G1a: unresolvable base ref → SystemExit non-zero with clear msg."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--base",
            "refs/heads/does-not-exist",
            "--head",
            "HEAD",
            "--json",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "cannot resolve ref" in proc.stderr
    assert "does-not-exist" in proc.stderr


def test_e2e_g1b_malformed_python_skipped_in_output(tmp_path: Path) -> None:
    """G1b: malformed `.py` at head → reported in skipped_files, exit 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "tests/test_z.py", "def f(): pass\n", msg="initial")
    _commit(
        repo,
        "tests/test_z.py",
        "def f(): pass\ndef broken(:\n    pass\n",
        msg="add syntax error",
    )
    proc = _invoke(repo)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["skipped_files"], data
    assert "syntax error" in data["skipped_files"][0]["reason"].lower()


def test_e2e_g1c_empty_diff_exit_0(tmp_path: Path) -> None:
    """G1c: base==head → empty diff, exit 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--base",
            "HEAD",
            "--head",
            "HEAD",
            "--json",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["matches"] == []


def test_e2e_typescript_file_ignored(tmp_path: Path) -> None:
    """Adversarial: vitest `.ts` file is silently skipped (out of scope)."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(
        repo,
        "src/test_x.ts",
        "test.each([\n  ['a', 1],\n])('case', (n, v) => {});\n",
        msg="initial vitest",
    )
    _commit(
        repo,
        "src/test_x.ts",
        ("test.each([\n  ['a', 1],\n  ['b', 2],\n])('case', (n, v) => {});\n"),
        msg="add row",
    )
    proc = _invoke(repo)
    # `.ts` files are out of scope; expect no matches and exit 0.
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["matches"] == []

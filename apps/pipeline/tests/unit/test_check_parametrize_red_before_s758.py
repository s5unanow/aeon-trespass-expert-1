"""S5U-758 follow-up tests for scripts/check_parametrize_red_before.py.

Three sub-gaps from S5U-650:
  (a) AST detector miss for `from pytest import mark; @mark.parametrize(...)`
  (b) `_read_head_blob` Rule G1 fail-open on `git show` failure
  (c) docstring claims exit 2 on degenerate input but impl exited 1

Split out from `test_check_parametrize_red_before.py` to keep the
co-located guard test file under the 400-line ceiling.
"""

from __future__ import annotations

import importlib.util
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


# -- (a) AST alias-import branch ------------------------------------------


def test_unit_pytest_mark_parametrize_alias_flagged(helper: ModuleType) -> None:
    """S5U-758 (a): `from pytest import mark; @mark.parametrize(...)` is detected.

    Red-before evidence cited in the commit message (pre-fix returns
    `([], [])`).
    """
    src = (
        "from pytest import mark\n\n"
        "@mark.parametrize('a,b', [\n"
        "    (1, 2),\n"
        "    (3, 4),\n"
        "])\n"
        "def test_x(a, b): pass\n"
    )
    matches, skips = helper.analyze_file("t.py", src, [4, 5])
    assert skips == []
    labels = {(m.line, m.context, m.function) for m in matches}
    assert labels == {
        (4, "mark.parametrize", "test_x"),
        (5, "mark.parametrize", "test_x"),
    }


def test_unit_pytest_mark_non_parametrize_attr_not_flagged(helper: ModuleType) -> None:
    """S5U-758 (a) false-positive guard: `@mark.skipif` is NOT flagged.

    The new branch's `inner.attr == "parametrize"` clause keeps any
    other `@mark.X` decorator from matching. Red-before: N/A — this
    test pins existing behavior (was not flagged pre-fix and remains
    so post-fix); the new branch is constrained by `attr ==
    "parametrize"`.
    """
    src = "from pytest import mark\n\n@mark.skipif(True, reason='nope')\ndef test_y(): pass\n"
    matches, _ = helper.analyze_file("t.py", src, [3])
    assert matches == []


# -- (b) `_read_head_blob` G1 fail-closed --------------------------------


def test_unit_read_head_blob_git_show_failure_fails_closed(
    helper: ModuleType, tmp_path: Path
) -> None:
    """S5U-758 (b): `_read_head_blob` raises SystemExit(2) on git-show failure.

    Pre-fix returned `None` silently (Rule G1 fail-open). Red-before
    evidence cited in the commit message.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    cwd_before = os.getcwd()
    try:
        os.chdir(repo)
        with pytest.raises(SystemExit) as exc_info:
            helper._read_head_blob("HEAD", "no/such/path.py")
        assert exc_info.value.code == 2
    finally:
        os.chdir(cwd_before)

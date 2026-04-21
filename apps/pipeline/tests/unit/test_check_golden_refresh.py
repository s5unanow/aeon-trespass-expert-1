"""Tests for scripts/check_golden_refresh.py (S5U-686).

Covers the fail-closed discipline from .claude/rules/guards.md Rule G1:
a missing base/head ref, a shallow-checkout scenario, a git diff
subprocess failure, or a `git log` failure MUST raise SystemExit — they
must not be silently converted into "no golden changes / no governance
violations."

Red-before anchor: these tests fail on pre-fix SHA a98571b (current main
at branch creation). The pre-fix guard exited 0 with "No golden fixture
files changed" on an unresolvable base ref; the new tests assert exit
!= 0.
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
SCRIPT_PATH = SCRIPT_DIR / "check_golden_refresh.py"

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


@pytest.fixture()
def guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_golden_refresh.py as a module for unit-level tests."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_golden_refresh", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_golden_refresh"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_golden_refresh", None)


def _run_git_cmd(repo: Path, *args: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "HOME": str(repo),
        "PATH": _PATH_ENV,
    }
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        env=env,
        capture_output=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    _run_git_cmd(repo, "config", "user.name", "Test")
    _run_git_cmd(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("test repo\n")
    _run_git_cmd(repo, "add", "README.md")
    _run_git_cmd(repo, "commit", "-q", "-m", "initial")


def _commit_file(repo: Path, rel_path: str, contents: str, *, message: str) -> None:
    full = repo / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(contents)
    _run_git_cmd(repo, "add", rel_path)
    _run_git_cmd(repo, "commit", "-q", "-m", message)


def _invoke_script(
    repo: Path,
    *,
    base: str = "HEAD~1",
    head: str = "HEAD",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--base", base, "--head", head],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


# --- Happy-path: legitimate no-op and legitimate refresh ---


def test_no_golden_changes_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "unrelated.txt", "hi\n", message="unrelated change")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "No golden fixture files changed" in proc.stdout


def test_golden_change_missing_meta_blocks(tmp_path: Path) -> None:
    """A golden refresh without _annotation_meta.toml update is a violation."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(
        repo,
        "packages/fixtures/sample_documents/fx/expected/out.json",
        "{}\n",
        message="refresh goldens: fx baseline",
    )
    proc = _invoke_script(repo)
    assert proc.returncode != 0
    assert "_annotation_meta.toml was not updated" in proc.stdout


# --- G1: fail-closed on degenerate inputs ---


def test_missing_base_ref_hard_errors(tmp_path: Path) -> None:
    """S5U-686 / G1: unresolvable base ref must fail closed."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "unrelated.txt", "hi\n", message="unrelated")
    proc = _invoke_script(repo, base="origin/nonexistent_base_ref_xyz")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    combined = (proc.stdout + proc.stderr).lower()
    assert "cannot resolve ref" in combined


def test_missing_head_ref_hard_errors(tmp_path: Path) -> None:
    """S5U-686 / G1: unresolvable head ref must fail closed (symmetry)."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "unrelated.txt", "hi\n", message="unrelated")
    proc = _invoke_script(repo, base="HEAD", head="nonexistent_head_ref_xyz")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "cannot resolve ref" in (proc.stdout + proc.stderr).lower()


def test_shallow_checkout_hard_errors(tmp_path: Path) -> None:
    """S5U-686 / G1: shallow checkout where the base commit is not fetched
    must fail closed. Simulated via `git clone --depth=1` then invoking
    the guard with HEAD~1 (unreachable in the shallow clone).
    """
    upstream = tmp_path / "upstream"
    _init_repo(upstream)
    _commit_file(upstream, "a.txt", "1\n", message="c1")
    _commit_file(upstream, "b.txt", "2\n", message="c2")

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth=1", f"file://{upstream}", str(shallow)],
        check=True,
        capture_output=True,
    )
    proc = _invoke_script(shallow, base="HEAD~1", head="HEAD")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "cannot resolve ref" in (proc.stdout + proc.stderr).lower()


def test_diff_subprocess_failure_hard_errors(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5U-686 / G1: if BOTH git diff invocations fail, the guard must
    raise SystemExit — not silently return []."""

    class _FakeCompleted:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        return _FakeCompleted(returncode=128, stderr="fatal: bad revision 'X...Y'")

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as excinfo:
        guard.get_changed_files("X", "Y")
    assert "git diff failed" in str(excinfo.value)


def test_git_log_subprocess_failure_hard_errors(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5U-686 / G1: `get_commits_touching_files` must raise SystemExit
    on `git log` non-zero exit — not silently return []. The prior
    behavior turned any ref/diff error into "no commits touched golden
    files → no governance violations."
    """

    class _FakeCompleted:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        return _FakeCompleted(returncode=128, stderr="fatal: bad revision")

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as excinfo:
        guard.get_commits_touching_files("X", "Y", ["some/path/*"])
    assert "git log" in str(excinfo.value)


def test_diff_primary_fails_fallback_succeeds_is_carve_out(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5U-686 legitimate carve-out: disjoint histories mean `A...B` has
    no merge-base and fails, but `A B` still works. We must NOT hard-fail
    — we must return the fallback output.
    """

    class _FakeCompleted:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    call_count = {"n": 0}

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeCompleted(returncode=128, stderr="fatal: no merge base")
        return _FakeCompleted(
            returncode=0,
            stdout="packages/fixtures/sample_documents/fx/expected/x.json\n",
        )

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    assert guard.get_changed_files("X", "Y") == [
        "packages/fixtures/sample_documents/fx/expected/x.json"
    ]

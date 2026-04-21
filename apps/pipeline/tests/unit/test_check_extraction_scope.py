"""Tests for scripts/check_extraction_scope.py (S5U-686).

Covers the fail-closed discipline from .claude/rules/guards.md Rule G1:
a missing base/head ref, a shallow-checkout scenario, or a git diff
subprocess failure MUST raise SystemExit — they must not be silently
converted into "no extraction scope."

Red-before anchor: these tests fail on pre-fix SHA a98571b (current main
at branch creation). The pre-fix guard exited 0 with areas=[] on an
unresolvable base ref; the new tests assert exit != 0.
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
SCRIPT_PATH = SCRIPT_DIR / "check_extraction_scope.py"

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


@pytest.fixture()
def guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_extraction_scope.py as a module for unit-level tests."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_extraction_scope", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_extraction_scope"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_extraction_scope", None)


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


# --- Happy-path: legitimate diffs still work ---


def test_valid_refs_with_no_changes_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "unrelated.txt", "hi\n", message="unrelated")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_valid_refs_with_extraction_change_detected(tmp_path: Path) -> None:
    """A file under an extraction-area glob is detected and flagged."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(
        repo,
        "apps/pipeline/src/atr_pipeline/stages/extract_native/foo.py",
        "x = 1\n",
        message="add extractor",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "primitive_extraction" in proc.stdout


def test_valid_refs_with_golden_change_detected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(
        repo,
        "packages/fixtures/sample_documents/fx/expected/out.json",
        "{}\n",
        message="golden",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"golden_refresh_detected": true' in proc.stdout


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
    """S5U-686 / G1: a shallow checkout where the base ref is not fetched
    must fail closed. We simulate this by cloning --depth=1 from an upstream
    where only the tip is reachable, then invoking the guard with a base
    ref that exists upstream but not in the shallow clone.
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
    # In the shallow clone, HEAD~1 is unreachable.
    proc = _invoke_script(shallow, base="HEAD~1", head="HEAD")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "cannot resolve ref" in (proc.stdout + proc.stderr).lower()


def test_diff_subprocess_failure_hard_errors(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5U-686 / G1: if BOTH `git diff A...B` and `git diff A B` fail
    (non-zero exit), the guard must raise SystemExit — not silently
    return []. Simulated via monkeypatched subprocess.run.
    """

    class _FakeCompleted:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        # Both primary and fallback git diff invocations fail.
        return _FakeCompleted(returncode=128, stderr="fatal: bad revision 'X...Y'")

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as excinfo:
        guard.get_changed_files("X", "Y")
    assert "git diff failed" in str(excinfo.value)


def test_diff_primary_fails_fallback_succeeds_is_carve_out(
    guard: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5U-686 legitimate carve-out (A6 in plan): disjoint histories mean
    `A...B` has no merge-base and fails, but `A B` still works. We must NOT
    hard-fail in this case — we must return the fallback output.
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
            # primary `A...B` fails
            return _FakeCompleted(returncode=128, stderr="fatal: no merge base")
        # fallback `A B` succeeds
        return _FakeCompleted(returncode=0, stdout="configs/qa/thresholds.toml\n")

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    assert guard.get_changed_files("X", "Y") == ["configs/qa/thresholds.toml"]

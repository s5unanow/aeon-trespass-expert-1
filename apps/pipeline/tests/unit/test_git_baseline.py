"""Characterization tests for scripts/_git_baseline.py (S5U-1232).

`scripts/_git_baseline.py` consolidates the `verify_ref_exists` /
`get_changed_files` git-baseline helpers that were copy-pasted (with drifting
signatures, and one latent fail-OPEN in check_code_erosion.py) across ~6
`scripts/check_*.py`. The consolidated helpers MUST fail closed on every
degenerate input per .claude/rules/guards.md Rule G1 (the S5U-642
retrospective): missing/unresolvable ref, shallow checkout, git subprocess
failure on BOTH diff tiers. The legitimate disjoint-history carve-out (A...B
fails, A B succeeds) must still pass.

Red-before per test:
- The happy-path and already-strict fail-closed cases pin an EXISTING invariant
  (the strict behavior already lived in 3 of the pre-extraction copies — e.g.
  check_extraction_scope.py / check_golden_refresh.py). Form:
  "N/A — characterization test pins existing invariant; pure refactor, no
  behavior change for the helper itself."
- `test_get_changed_files_double_diff_failure_raises` additionally guards the
  ONE fail-open that DID exist (check_code_erosion.py returned [] here). To
  prove this test catches a permissive regression, the helper was temporarily
  mutated to `return []` on double-fail (the old code_erosion behavior); the
  test went RED ("DID NOT RAISE <class 'SystemExit'>"), then the mutation was
  reverted. Form-(b) local-run red-before; mutation never committed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "_git_baseline.py"


@pytest.fixture()
def gb(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import scripts/_git_baseline.py as a fresh module per test."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("_git_baseline", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_git_baseline"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_git_baseline", None)


# --- git-repo helpers ---------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("repo\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")


def _commit_file(repo: Path, rel: str, contents: str, *, message: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(contents)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- verify_ref_exists --------------------------------------------------------


def test_verify_ref_exists_passes_for_real_ref(gb: ModuleType, tmp_path: Path) -> None:
    """Happy-path: a resolvable ref does not raise.

    Red-before: N/A — characterization test pins existing invariant.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    # Returns None (no raise). cwd pins git to the repo.
    assert gb.verify_ref_exists("HEAD", cwd=str(repo)) is None


def test_verify_ref_exists_missing_ref_raises(gb: ModuleType, tmp_path: Path) -> None:
    """Failure input: an unresolvable ref must fail closed (Rule G1).

    Red-before: N/A — characterization test pins existing invariant.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    with pytest.raises(SystemExit) as excinfo:
        gb.verify_ref_exists("definitely-not-a-ref", cwd=str(repo))
    assert "cannot resolve ref" in str(excinfo.value).lower()


def test_verify_ref_exists_shallow_checkout_raises(gb: ModuleType, tmp_path: Path) -> None:
    """Adversarial (Rule G1 required shallow scenario): a shallow clone where
    HEAD~1 is unfetched must fail closed, not silently treat the base as absent.

    Red-before: N/A — characterization test pins existing invariant.
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
    with pytest.raises(SystemExit) as excinfo:
        gb.verify_ref_exists("HEAD~1", cwd=str(shallow))
    assert "cannot resolve ref" in str(excinfo.value).lower()


# --- get_changed_files --------------------------------------------------------


def test_get_changed_files_returns_changed(gb: ModuleType, tmp_path: Path) -> None:
    """Happy-path: real two-commit repo returns the changed file list.

    Red-before: N/A — characterization test pins existing invariant.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/x.py", "print(1)\n", message="add x")
    changed = gb.get_changed_files("HEAD~1", "HEAD", cwd=str(repo))
    assert changed == ["src/x.py"]


def test_get_changed_files_double_diff_failure_raises(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure input + the FIXED fail-open: when BOTH the `A...B` and `A B`
    diffs fail, the helper must raise SystemExit — never silently return [].
    check_code_erosion.py's pre-extraction copy returned [] here (Rule G1
    fail-open); the consolidated helper fails closed.

    Red-before: form-(b) — temporarily mutating this helper to `return []` on
    double-fail (the old code_erosion behavior) made this test RED locally
    ("DID NOT RAISE SystemExit"); mutation reverted, never committed.
    """

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        return _FakeCompleted(returncode=128, stderr="fatal: bad revision 'X...Y'")

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as excinfo:
        gb.get_changed_files("X", "Y")
    assert "git diff failed" in str(excinfo.value)


def test_get_changed_files_primary_fail_fallback_ok_carveout(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adversarial carve-out: disjoint histories make `A...B` fail (no
    merge-base) but `A B` still works — must return the fallback output, NOT
    hard-fail.

    Red-before: N/A — characterization test pins existing invariant.
    """
    calls = {"n": 0}

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeCompleted(returncode=128, stderr="fatal: no merge base")
        return _FakeCompleted(returncode=0, stdout="pkg/a.py\npkg/b.py\n")

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    assert gb.get_changed_files("X", "Y") == ["pkg/a.py", "pkg/b.py"]


def test_get_changed_files_empty_diff_returns_empty_list(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine no-op diff (rc=0, empty stdout) returns [] — git SUCCEEDED, so
    this is NOT a fail-closed case.

    Red-before: N/A — characterization test pins existing invariant.
    """

    def fake_run(cmd: list[str], **_kwargs: object) -> _FakeCompleted:
        return _FakeCompleted(returncode=0, stdout="")

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    assert gb.get_changed_files("X", "Y") == []


def test_get_changed_files_cwd_is_threaded(gb: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """The `cwd` kwarg must be forwarded to every git invocation so the diff
    stays pinned to the intended repo root (check_detector_corpus_coverage
    relies on this to align with --repo-root).

    Red-before: N/A — characterization test pins existing invariant.
    """
    seen: list[str | None] = []

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        seen.append(kwargs.get("cwd"))  # type: ignore[arg-type]
        return _FakeCompleted(returncode=0, stdout="x.py\n")

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    gb.get_changed_files("A", "B", cwd="/some/root")
    assert seen == ["/some/root"]

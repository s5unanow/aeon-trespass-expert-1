"""Tests for scripts/check_detector_corpus_coverage.py (S5U-789, criterion 4).

Covers, per .claude/rules/guards.md:

* Rule G1 fail-closed: unresolvable base ref (shallow checkout), git-diff
  failure, malformed corpus TOML, missing/empty `detector_sources`, a
  `detector_sources` path that does not exist, and a missing corpus directory.
* Three-input behavioral: detector+corpus changed (allow), detector-only
  changed (block), corpus-only / unrelated change (allow).
* Self-bypass: a corpus pointing at a nonexistent detector fails closed.

Red-before confirmation: N/A — these tests pin the behavior of a NEW script
(`check_detector_corpus_coverage.py`) introduced in this PR. There is no
pre-fix production state to revert; the script did not exist at the branch
base `0a290f1`. Reviewer asked to cross-check the diff (the script and these
tests land together).

`corpus_cov` fixture is auto-discovered from tests/unit/conftest.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DETECTOR_REL = "scripts/check_visual_test_overrides.py"
_CORPUS_REL = "apps/pipeline/tests/safety_gate_corpus/maxdiffpixelratio.toml"
_CORPUS_TOML = f'policy = "maxdiffpixelratio"\ndetector_sources = ["{_DETECTOR_REL}"]\n'


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> None:
    """Repo with a base commit carrying a detector source + its corpus."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _write(root, _DETECTOR_REL, "# detector v1\n")
    _write(root, _CORPUS_REL, _CORPUS_TOML)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")


def _make_corpus_dir(root: Path, body: str = _CORPUS_TOML) -> Path:
    """Build a non-git corpus tree for load_policies tests; return repo root."""
    _write(root, _DETECTOR_REL, "# detector\n")
    _write(root, _CORPUS_REL, body)
    return root


# ---------------------------------------------------------------------------
# load_policies — discovery + Rule G1 fail-closed
# ---------------------------------------------------------------------------


def test_load_policies_happy(corpus_cov: ModuleType, tmp_path: Path) -> None:
    root = _make_corpus_dir(tmp_path)
    policies = corpus_cov.load_policies(root, corpus_cov.DEFAULT_CORPUS_DIR)
    assert len(policies) == 1
    assert policies[0].name == "maxdiffpixelratio"
    assert policies[0].corpus_rel == _CORPUS_REL
    assert policies[0].detector_sources == (_DETECTOR_REL,)


def test_missing_corpus_dir_fails_closed(corpus_cov: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="corpus directory"):
        corpus_cov.load_policies(tmp_path, corpus_cov.DEFAULT_CORPUS_DIR)


def test_malformed_corpus_fails_closed(corpus_cov: ModuleType, tmp_path: Path) -> None:
    root = _make_corpus_dir(tmp_path, body='policy = "x"\ndetector_sources = [unclosed\n')
    with pytest.raises(SystemExit, match="cannot parse corpus"):
        corpus_cov.load_policies(root, corpus_cov.DEFAULT_CORPUS_DIR)


def test_missing_detector_sources_fails_closed(corpus_cov: ModuleType, tmp_path: Path) -> None:
    root = _make_corpus_dir(tmp_path, body='policy = "maxdiffpixelratio"\n')
    with pytest.raises(SystemExit, match="detector_sources"):
        corpus_cov.load_policies(root, corpus_cov.DEFAULT_CORPUS_DIR)


def test_empty_detector_sources_fails_closed(corpus_cov: ModuleType, tmp_path: Path) -> None:
    root = _make_corpus_dir(tmp_path, body='policy = "maxdiffpixelratio"\ndetector_sources = []\n')
    with pytest.raises(SystemExit, match="detector_sources"):
        corpus_cov.load_policies(root, corpus_cov.DEFAULT_CORPUS_DIR)


def test_missing_policy_key_fails_closed(corpus_cov: ModuleType, tmp_path: Path) -> None:
    root = _make_corpus_dir(tmp_path, body=f'detector_sources = ["{_DETECTOR_REL}"]\n')
    with pytest.raises(SystemExit, match="policy"):
        corpus_cov.load_policies(root, corpus_cov.DEFAULT_CORPUS_DIR)


def test_corpus_sources_nonexistent_path_fails_closed(
    corpus_cov: ModuleType, tmp_path: Path
) -> None:
    """Self-bypass guard: a corpus pointing at a missing detector cannot verify."""
    body = 'policy = "ghost"\ndetector_sources = ["scripts/does_not_exist.py"]\n'
    _write(tmp_path, "apps/pipeline/tests/safety_gate_corpus/ghost.toml", body)
    with pytest.raises(SystemExit, match="not exist on disk"):
        corpus_cov.load_policies(tmp_path, corpus_cov.DEFAULT_CORPUS_DIR)


# ---------------------------------------------------------------------------
# find_violations — three-input behavioral (pure function)
# ---------------------------------------------------------------------------


def _policy(corpus_cov: ModuleType) -> object:
    return corpus_cov.Policy(
        name="maxdiffpixelratio",
        corpus_rel=_CORPUS_REL,
        detector_sources=(_DETECTOR_REL,),
    )


def test_detector_and_corpus_changed_allows(corpus_cov: ModuleType) -> None:
    changed = {_DETECTOR_REL, _CORPUS_REL}
    assert corpus_cov.find_violations([_policy(corpus_cov)], changed) == []


def test_detector_changed_corpus_unchanged_blocks(corpus_cov: ModuleType) -> None:
    changed = {_DETECTOR_REL}
    violations = corpus_cov.find_violations([_policy(corpus_cov)], changed)
    assert len(violations) == 1
    assert "maxdiffpixelratio" in violations[0]


def test_corpus_only_change_allows(corpus_cov: ModuleType) -> None:
    """A waiver/comment-only corpus edit (no detector change) never blocks."""
    changed = {_CORPUS_REL}
    assert corpus_cov.find_violations([_policy(corpus_cov)], changed) == []


def test_unrelated_change_allows(corpus_cov: ModuleType) -> None:
    changed = {"apps/web/src/foo.tsx", "docs/x.md"}
    assert corpus_cov.find_violations([_policy(corpus_cov)], changed) == []


def test_only_violating_policy_reported(corpus_cov: ModuleType) -> None:
    clean = corpus_cov.Policy(
        name="other",
        corpus_rel="apps/pipeline/tests/safety_gate_corpus/other.toml",
        detector_sources=("scripts/check_other.py",),
    )
    changed = {_DETECTOR_REL}  # touches only the maxdiff detector
    violations = corpus_cov.find_violations([_policy(corpus_cov), clean], changed)
    assert len(violations) == 1
    assert "maxdiffpixelratio" in violations[0]


# ---------------------------------------------------------------------------
# Rule G1 — git-level fail-closed (real repos)
# ---------------------------------------------------------------------------


def test_unresolvable_base_fails_closed(
    corpus_cov: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S5U-1232: _verify_ref_exists was consolidated into scripts/_git_baseline.py
    # and re-exported via the caller's `from _git_baseline import verify_ref_exists`.
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="cannot resolve ref"):
        corpus_cov.verify_ref_exists("origin/nonexistent-base")


def test_diff_failure_fails_closed_outside_repo(
    corpus_cov: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # not a git repo → both diff tiers fail
    with pytest.raises(SystemExit, match="git diff failed"):
        corpus_cov.get_changed_files("HEAD~1", "HEAD")


# ---------------------------------------------------------------------------
# main() — end-to-end against a real two-commit repo
# ---------------------------------------------------------------------------


def test_main_blocks_detector_change_without_corpus(
    corpus_cov: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, _DETECTOR_REL, "# detector v2 (added a regex)\n")
    _git(tmp_path, "commit", "-aq", "-m", "change detector only")
    monkeypatch.chdir(tmp_path)
    rc = corpus_cov.main(["--base", "HEAD~1", "--head", "HEAD", "--repo-root", str(tmp_path)])
    assert rc == 1


def test_main_allows_detector_change_with_corpus(
    corpus_cov: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, _DETECTOR_REL, "# detector v2\n")
    _write(tmp_path, _CORPUS_REL, _CORPUS_TOML + "# coverage-waiver: S5U-789 net-zero\n")
    _git(tmp_path, "commit", "-aq", "-m", "change detector + corpus")
    monkeypatch.chdir(tmp_path)
    rc = corpus_cov.main(["--base", "HEAD~1", "--head", "HEAD", "--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_allows_unrelated_change(
    corpus_cov: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "apps/web/src/foo.tsx", "export const x = 1;\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "unrelated")
    monkeypatch.chdir(tmp_path)
    rc = corpus_cov.main(["--base", "HEAD~1", "--head", "HEAD", "--repo-root", str(tmp_path)])
    assert rc == 0

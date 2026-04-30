"""End-to-end happy-path tests for scripts/check_threshold_changes.py.

S5U-656 split-out from the original test_check_threshold_changes.py: the
happy-path E2E tests (real git repo + real subprocess) live here. The
companion failure / adversarial / wire E2E tests live in
test_check_threshold_changes_e2e_bypass.py. Shared helpers (git repo
setup, subprocess invocation, TOML constants) live in
_threshold_test_helpers.py.
"""

from __future__ import annotations

from pathlib import Path

from ._threshold_test_helpers import (
    TOML_SIMPLE,
    _init_repo_with_base,
    _invoke_script,
    _make_head_commit,
    _run_git_cmd,
)


def test_no_threshold_change_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    (repo / "other.txt").write_text("x")
    _run_git_cmd(repo, "add", "other.txt")
    _run_git_cmd(repo, "commit", "-q", "-m", "unrelated change")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_tightening_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    tightened = TOML_SIMPLE.replace("min = 0.98", "min = 0.99")
    _make_head_commit(repo, tightened, message="tighten")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no loosening" in proc.stdout.lower()


def test_loosening_with_named_commit_sentinel_passes(tmp_path: Path) -> None:
    """S5U-643: sentinel on the responsible commit, naming the threshold, passes."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(
        repo,
        loosened,
        message="loosen a_pass_rate\n\nLOOSEN-THRESHOLD: a_pass_rate — recalibrated 2026-04",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "justified by commit" in proc.stdout


def test_loosening_with_named_pr_body_bullet_passes(tmp_path: Path) -> None:
    """S5U-643: PR body bullet naming the threshold covers the finding."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen a_pass_rate")
    pr_body = (
        "## Summary\n\nloosen\n\n"
        "## Threshold loosening justification\n\n"
        "- a_pass_rate: dataset drift confirmed, audit linked\n"
    )
    proc = _invoke_script(repo, pr_body=pr_body)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PR body" in proc.stdout

"""Tests for scripts/check_threshold_changes.py (S5U-591).

Every test here corresponds to a row in `tmp/plan-s5u-591.md` adversarial
matrix. Unit tests poke the pure helpers directly; end-to-end tests spin
up a temporary git repo and invoke the script as a subprocess, mirroring
how CI calls it.

Red-before discipline (S5U-615): each test targets a distinct code path
in the script. Running these against a stripped-down stub of the script
(e.g. one that always returns 0) causes the failure-input tests
(`test_loosening_*`, `test_deletion_blocks`, etc.) to fail with a clear
assertion, confirming they exercise the real branching. The happy-path
tests in turn fail against a stub that always returns 1. Both failure
modes are observable without mock scaffolding.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_threshold_changes.py"


@pytest.fixture()
def guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_threshold_changes.py as a module."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_threshold_changes", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_threshold_changes"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_threshold_changes", None)


# ---------------------------------------------------------------------------
# Unit tests — pure helpers
# ---------------------------------------------------------------------------


TOML_BASE = """\
version = 1

[[metric_thresholds]]
name = "a_pass_rate"
min = 0.98
blocking = true
description = "A"

[[metric_thresholds]]
name = "b_pass_rate"
min = 0.90
blocking = true
description = "B"
"""


class TestParseThresholds:
    def test_missing_file_returns_empty(self, guard: ModuleType) -> None:
        assert guard._parse_thresholds(None) == {}

    def test_well_formed_returns_entries(self, guard: ModuleType) -> None:
        parsed = guard._parse_thresholds(TOML_BASE)
        assert set(parsed.keys()) == {"a_pass_rate", "b_pass_rate"}
        assert parsed["a_pass_rate"].min == 0.98
        assert parsed["a_pass_rate"].blocking is True

    def test_entry_without_name_skipped(self, guard: ModuleType) -> None:
        toml = textwrap.dedent(
            """
            [[metric_thresholds]]
            min = 0.9

            [[metric_thresholds]]
            name = "ok"
            min = 0.8
            """
        )
        parsed = guard._parse_thresholds(toml)
        assert set(parsed.keys()) == {"ok"}

    def test_entry_without_min_skipped(self, guard: ModuleType) -> None:
        toml = textwrap.dedent(
            """
            [[metric_thresholds]]
            name = "no_min"

            [[metric_thresholds]]
            name = "ok"
            min = 0.8
            """
        )
        parsed = guard._parse_thresholds(toml)
        assert set(parsed.keys()) == {"ok"}

    def test_malformed_toml_raises(self, guard: ModuleType) -> None:
        with pytest.raises(SystemExit):
            guard._parse_thresholds("this is {{{ not valid TOML")


class TestDetectLoosening:
    def test_identical_no_findings(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        assert guard.detect_loosening(base, dict(base)) == []

    def test_min_lowered_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.80, blocking=True)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].name == "a_pass_rate"
        assert findings[0].kind == "min_lowered"

    def test_min_raised_no_finding(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.99, blocking=True)
        assert guard.detect_loosening(base, head) == []

    def test_entry_deleted_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = {k: v for k, v in base.items() if k != "b_pass_rate"}
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].kind == "deleted"

    def test_blocking_flip_to_false_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.98, blocking=False)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].kind == "blocking_disabled"

    def test_net_new_entry_no_finding(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["c_new"] = guard.ThresholdEntry(name="c_new", min=0.5, blocking=True)
        assert guard.detect_loosening(base, head) == []

    def test_tighten_plus_loosen_reports_loosen(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.99, blocking=True)
        head["b_pass_rate"] = guard.ThresholdEntry(name="b_pass_rate", min=0.50, blocking=True)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].name == "b_pass_rate"


class TestCommitSentinel:
    def test_non_empty_reason_matches(self, guard: ModuleType) -> None:
        ok, reason = guard.has_commit_sentinel(
            ["S5U-XXX: something\n\nLOOSEN-THRESHOLD: recalibrated 2026-04"]
        )
        assert ok is True
        assert "recalibrated" in reason

    def test_case_insensitive(self, guard: ModuleType) -> None:
        ok, _ = guard.has_commit_sentinel(["loosen-threshold: dataset refresh"])
        assert ok is True

    def test_empty_reason_rejected(self, guard: ModuleType) -> None:
        ok, _ = guard.has_commit_sentinel(["LOOSEN-THRESHOLD:   "])
        assert ok is False

    def test_missing_sentinel(self, guard: ModuleType) -> None:
        ok, _ = guard.has_commit_sentinel(["S5U-XXX: normal commit"])
        assert ok is False

    def test_sentinel_in_one_of_many(self, guard: ModuleType) -> None:
        msgs = [
            "S5U-XXX: prep",
            "S5U-XXX: calibration\nLOOSEN-THRESHOLD: dataset refresh",
        ]
        ok, reason = guard.has_commit_sentinel(msgs)
        assert ok is True
        assert "dataset refresh" in reason


class TestPrBodySentinel:
    def test_heading_with_body_matches(self, guard: ModuleType, tmp_path: Path) -> None:
        body = textwrap.dedent(
            """
            ## Summary

            Change to thresholds.

            ## Threshold loosening justification

            Dataset was recalibrated on 2026-04-10; see audit report.
            """
        )
        f = tmp_path / "pr_body.md"
        f.write_text(body)
        ok, excerpt = guard.has_pr_body_sentinel(f)
        assert ok is True
        assert "Dataset" in excerpt

    def test_heading_without_body_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        body = "## Threshold loosening justification\n\n## Next section\n"
        f = tmp_path / "pr_body.md"
        f.write_text(body)
        ok, _ = guard.has_pr_body_sentinel(f)
        assert ok is False

    def test_no_heading_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        f = tmp_path / "pr_body.md"
        f.write_text("## Summary\n\nBody\n")
        ok, _ = guard.has_pr_body_sentinel(f)
        assert ok is False

    def test_missing_file_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        ok, _ = guard.has_pr_body_sentinel(tmp_path / "does_not_exist.md")
        assert ok is False

    def test_none_path_rejected(self, guard: ModuleType) -> None:
        ok, _ = guard.has_pr_body_sentinel(None)
        assert ok is False


# ---------------------------------------------------------------------------
# End-to-end: real git repo, real subprocess
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    full_env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    if env:
        full_env.update(env)
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        env={**full_env, "HOME": str(repo), "PATH": _PATH_ENV},
        capture_output=True,
    )


import os  # noqa: E402

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


def _init_repo_with_base(
    repo: Path,
    base_toml: str,
    *,
    commit_base_path: bool = True,
) -> None:
    """Initialize a git repo with a 'base' commit containing the thresholds file."""
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Ensure git can commit without global config.
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("test repo\n")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-q", "-m", "initial")
    if commit_base_path:
        cfg = repo / "configs" / "qa"
        cfg.mkdir(parents=True)
        (cfg / "thresholds.toml").write_text(base_toml)
        _run_git(repo, "add", "configs/qa/thresholds.toml")
        _run_git(repo, "commit", "-q", "-m", "base thresholds")


def _make_head_commit(
    repo: Path,
    head_toml: str | None,
    *,
    message: str,
) -> None:
    path = repo / "configs" / "qa" / "thresholds.toml"
    if head_toml is None:
        if path.exists():
            _run_git(repo, "rm", "-q", "configs/qa/thresholds.toml")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(head_toml)
        _run_git(repo, "add", "configs/qa/thresholds.toml")
    _run_git(repo, "commit", "-q", "-m", message)


def _invoke_script(
    repo: Path,
    *,
    pr_body: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args: list[str] = [
        sys.executable,
        str(SCRIPT_PATH),
        "--base",
        "HEAD~1",
        "--head",
        "HEAD",
    ]
    if pr_body is not None:
        body_file = repo / "pr_body.md"
        body_file.write_text(pr_body)
        args.extend(["--pr-body-file", str(body_file)])
    return subprocess.run(
        args,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


TOML_SIMPLE = textwrap.dedent(
    """\
    version = 1

    [[metric_thresholds]]
    name = "a_pass_rate"
    min = 0.98
    blocking = true
    description = "A metric"
    """
)


def test_no_threshold_change_passes(tmp_path: Path) -> None:
    """Happy path: file unchanged → guard passes."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    # A head commit that does NOT touch the thresholds file.
    (repo / "other.txt").write_text("x")
    _run_git(repo, "add", "other.txt")
    _run_git(repo, "commit", "-q", "-m", "unrelated change")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "unchanged" in proc.stdout.lower() or "no loosening" in proc.stdout.lower()


def test_tightening_passes(tmp_path: Path) -> None:
    """Happy path: raising min → guard passes."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    tightened = TOML_SIMPLE.replace("min = 0.98", "min = 0.99")
    _make_head_commit(repo, tightened, message="tighten")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no loosening" in proc.stdout.lower()


def test_loosening_without_justification_blocks(tmp_path: Path) -> None:
    """Failure input: lowering min without justification → exit 1."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen without reason")
    proc = _invoke_script(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "BLOCK" in proc.stdout
    assert "a_pass_rate" in proc.stdout


def test_loosening_with_commit_sentinel_passes(tmp_path: Path) -> None:
    """Adversarial: commit-message sentinel justifies loosening."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(
        repo,
        loosened,
        message="loosen a_pass_rate\n\nLOOSEN-THRESHOLD: recalibrated after dataset refresh",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Justification found in commit message" in proc.stdout


def test_loosening_with_pr_body_sentinel_passes(tmp_path: Path) -> None:
    """Adversarial: PR-body sentinel justifies loosening."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen a_pass_rate")
    pr_body = (
        "## Summary\n\nloosen\n\n## Threshold loosening justification\n\n"
        "Audit report linked; dataset drift moved mean to 0.82.\n"
    )
    proc = _invoke_script(repo, pr_body=pr_body)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PR body" in proc.stdout


def test_mixed_tighten_and_loosen_blocks(tmp_path: Path) -> None:
    """Adversarial: tightening one metric does not excuse loosening another."""
    repo = tmp_path / "repo"
    multi = textwrap.dedent(
        """\
        version = 1

        [[metric_thresholds]]
        name = "a_pass_rate"
        min = 0.98
        blocking = true
        description = "A"

        [[metric_thresholds]]
        name = "b_pass_rate"
        min = 0.90
        blocking = true
        description = "B"
        """
    )
    _init_repo_with_base(repo, multi)
    # Tighten A from 0.98 -> 0.99, loosen B from 0.90 -> 0.50.
    mixed = multi.replace("min = 0.98", "min = 0.99").replace("min = 0.90", "min = 0.50")
    _make_head_commit(repo, mixed, message="mixed")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "b_pass_rate" in proc.stdout
    # A was tightened, should not appear as a loosening finding.
    assert "a_pass_rate: min_lowered" not in proc.stdout


def test_deletion_blocks(tmp_path: Path) -> None:
    """Adversarial: removing a [[metric_thresholds]] entry is loosening."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    _make_head_commit(
        repo,
        "version = 1\n",  # entry removed entirely
        message="delete a_pass_rate",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "deleted" in proc.stdout


def test_rename_blocks(tmp_path: Path) -> None:
    """Adversarial: renaming a threshold is delete+add → blocks."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    renamed = TOML_SIMPLE.replace('name = "a_pass_rate"', 'name = "renamed_pass_rate"')
    _make_head_commit(repo, renamed, message="rename")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "a_pass_rate" in proc.stdout
    assert "deleted" in proc.stdout


def test_blocking_flip_to_false_blocks(tmp_path: Path) -> None:
    """Adversarial: flipping blocking=true → false weakens the gate."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    flipped = TOML_SIMPLE.replace("blocking = true", "blocking = false")
    _make_head_commit(repo, flipped, message="disable blocking")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "blocking_disabled" in proc.stdout


def test_reorder_only_passes(tmp_path: Path) -> None:
    """Happy path: reordering entries doesn't change thresholds."""
    repo = tmp_path / "repo"
    multi = textwrap.dedent(
        """\
        version = 1

        [[metric_thresholds]]
        name = "a_pass_rate"
        min = 0.98
        blocking = true
        description = "A"

        [[metric_thresholds]]
        name = "b_pass_rate"
        min = 0.90
        blocking = true
        description = "B"
        """
    )
    reordered = textwrap.dedent(
        """\
        version = 1

        [[metric_thresholds]]
        name = "b_pass_rate"
        min = 0.90
        blocking = true
        description = "B"

        [[metric_thresholds]]
        name = "a_pass_rate"
        min = 0.98
        blocking = true
        description = "A"
        """
    )
    _init_repo_with_base(repo, multi)
    _make_head_commit(repo, reordered, message="reorder")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no loosening" in proc.stdout.lower()


def test_description_only_change_passes(tmp_path: Path) -> None:
    """Happy path: changing description text doesn't affect the gate."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    edited = TOML_SIMPLE.replace('description = "A metric"', 'description = "A metric (refined)"')
    _make_head_commit(repo, edited, message="doc only")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_empty_sentinel_blocks(tmp_path: Path) -> None:
    """Adversarial: `LOOSEN-THRESHOLD:` with empty reason does not count."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen\n\nLOOSEN-THRESHOLD: ")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "BLOCK" in proc.stdout


def test_no_thresholds_file_at_base(tmp_path: Path) -> None:
    """Happy path: file didn't exist at base — new config can't loosen itself."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, "", commit_base_path=False)
    _make_head_commit(repo, TOML_SIMPLE, message="introduce thresholds")
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_base_had_file_head_deleted(tmp_path: Path) -> None:
    """Adversarial: deleting the whole thresholds file → blocks (loosens everything)."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    _make_head_commit(repo, None, message="nuke thresholds")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "deleted" in proc.stdout

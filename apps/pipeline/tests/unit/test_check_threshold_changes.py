"""Tests for scripts/check_threshold_changes.py (S5U-591, S5U-642, S5U-643, S5U-644).

Unit tests poke the pure helpers directly; end-to-end tests spin up a
temporary git repo and invoke the script as a subprocess, mirroring how
CI calls it.

S5U-643 per-finding tests (responsible-commit resolution + named-threshold
sentinel) carry red-before evidence. The pre-S5U-643 baseline lives at
`/tmp/s5u-643-redbefore/check_threshold_changes_baseline.py` (snapshot of
`scripts/check_threshold_changes.py` at SHA `cbd0256`). Running the new
adversarial tests against that baseline demonstrates the old free-form
sentinel accepts the decoy-commit-A / silent-loosen-commit-B exploit
that S5U-643 now blocks.
"""

from __future__ import annotations

import importlib.util
import os
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

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


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
        toml = '[[metric_thresholds]]\nmin = 0.9\n\n[[metric_thresholds]]\nname = "ok"\nmin = 0.8\n'
        assert set(guard._parse_thresholds(toml).keys()) == {"ok"}

    def test_entry_without_min_skipped(self, guard: ModuleType) -> None:
        toml = (
            '[[metric_thresholds]]\nname = "no_min"\n\n'
            '[[metric_thresholds]]\nname = "ok"\nmin = 0.8\n'
        )
        assert set(guard._parse_thresholds(toml).keys()) == {"ok"}

    def test_malformed_toml_raises(self, guard: ModuleType) -> None:
        with pytest.raises(SystemExit):
            guard._parse_thresholds("this is {{{ not valid TOML")

    @pytest.mark.parametrize(
        "blocking_value",
        ['"false"', '"true"', "1", "0"],
        ids=["str-false", "str-true", "int-1", "int-0"],
    )
    def test_blocking_non_bool_rejected(self, guard: ModuleType, blocking_value: str) -> None:
        """S5U-644: string "false" (truthy), "true", int 1/0 all must raise."""
        toml = f'[[metric_thresholds]]\nname = "x"\nmin = 0.5\nblocking = {blocking_value}\n'
        with pytest.raises(SystemExit, match="must be a TOML boolean"):
            guard._parse_thresholds(toml)


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


class TestCommitSentinelCovers:
    """S5U-643: per-finding, named sentinel matching."""

    @pytest.mark.parametrize(
        "sep",
        ["—", "--", "-", ":"],
        ids=["em-dash", "double-hyphen", "hyphen", "colon"],
    )
    def test_named_threshold_with_any_valid_separator_matches(
        self, guard: ModuleType, sep: str
    ) -> None:
        """S5U-643: all four separator forms accepted (`—`, `--`, `-`, `:`)."""
        msg = f"LOOSEN-THRESHOLD: a_pass_rate {sep} dataset refresh"
        ok, reason = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is True
        assert "dataset refresh" in reason

    def test_case_insensitive_sentinel(self, guard: ModuleType) -> None:
        msg = "loosen-threshold: A_Pass_Rate — dataset refresh"
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is True

    def test_multi_name_list_covers_each(self, guard: ModuleType) -> None:
        msg = "LOOSEN-THRESHOLD: a_pass_rate, b_pass_rate — joint recalibration"
        assert guard.commit_sentinel_covers("a_pass_rate", msg)[0] is True
        assert guard.commit_sentinel_covers("b_pass_rate", msg)[0] is True

    def test_wrong_threshold_name_rejected(self, guard: ModuleType) -> None:
        """S5U-643: sentinel naming a different threshold does not cover ours."""
        msg = "LOOSEN-THRESHOLD: a_pass_rate — reason"
        ok, _ = guard.commit_sentinel_covers("b_pass_rate", msg)
        assert ok is False

    def test_free_form_no_name_rejected(self, guard: ModuleType) -> None:
        """S5U-643: the old `LOOSEN-THRESHOLD: <reason>` grammar is retired.

        Red-before confirmation: ran
        `/tmp/s5u-643-redbefore/check_threshold_changes_baseline.py`'s
        `has_commit_sentinel(["LOOSEN-THRESHOLD: recalibrated"])` → returned
        (True, 'recalibrated'). The new `commit_sentinel_covers('a_pass_rate',
        ...)` returns (False, '') for the same input, enforcing per-finding
        binding.
        """
        msg = "LOOSEN-THRESHOLD: recalibrated"
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is False

    def test_empty_reason_rejected(self, guard: ModuleType) -> None:
        msg = "LOOSEN-THRESHOLD: a_pass_rate —   "
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is False

    def test_missing_sentinel(self, guard: ModuleType) -> None:
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", "S5U-XXX: normal commit")
        assert ok is False


class TestPrBodyCovers:
    @staticmethod
    def _write(tmp_path: Path, body: str) -> Path:
        f = tmp_path / "pr_body.md"
        f.write_text(body)
        return f

    def test_bullet_matches(self, guard: ModuleType, tmp_path: Path) -> None:
        body = (
            "## Summary\n\nChange.\n\n"
            "## Threshold loosening justification\n\n"
            "- a_pass_rate: dataset recalibrated 2026-04-10\n"
            "- b_pass_rate: see audit report\n"
        )
        f = self._write(tmp_path, body)
        ok, reason = guard.pr_body_covers("a_pass_rate", f)
        assert ok is True
        assert "recalibrated" in reason
        assert guard.pr_body_covers("b_pass_rate", f)[0] is True

    def test_bullet_for_different_threshold_rejected(
        self, guard: ModuleType, tmp_path: Path
    ) -> None:
        """S5U-643: coverage is per-finding; bullets for other names don't help."""
        f = self._write(tmp_path, "## Threshold loosening justification\n\n- a_pass_rate: reason\n")
        assert guard.pr_body_covers("b_pass_rate", f)[0] is False

    def test_heading_without_bullets_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        f = self._write(tmp_path, "## Threshold loosening justification\n\n## Next section\n")
        assert guard.pr_body_covers("a_pass_rate", f)[0] is False

    def test_bullet_outside_section_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        """S5U-643: bullets must be under the designated heading, not elsewhere."""
        body = (
            "## Other section\n\n- a_pass_rate: reason\n\n"
            "## Threshold loosening justification\n\n(empty)\n"
        )
        assert guard.pr_body_covers("a_pass_rate", self._write(tmp_path, body))[0] is False

    def test_missing_file_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        assert guard.pr_body_covers("a_pass_rate", tmp_path / "nope.md")[0] is False

    def test_none_path_rejected(self, guard: ModuleType) -> None:
        assert guard.pr_body_covers("a_pass_rate", None)[0] is False


# --- End-to-end: real git repo, real subprocess ---


def _run_git_cmd(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
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


def _init_repo_with_base(
    repo: Path,
    base_toml: str,
    *,
    commit_base_path: bool = True,
) -> None:
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
    if commit_base_path:
        cfg = repo / "configs" / "qa"
        cfg.mkdir(parents=True)
        (cfg / "thresholds.toml").write_text(base_toml)
        _run_git_cmd(repo, "add", "configs/qa/thresholds.toml")
        _run_git_cmd(repo, "commit", "-q", "-m", "base thresholds")


def _make_head_commit(repo: Path, head_toml: str | None, *, message: str) -> None:
    path = repo / "configs" / "qa" / "thresholds.toml"
    if head_toml is None:
        if path.exists():
            _run_git_cmd(repo, "rm", "-q", "configs/qa/thresholds.toml")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(head_toml)
        _run_git_cmd(repo, "add", "configs/qa/thresholds.toml")
    _run_git_cmd(repo, "commit", "-q", "-m", message)


def _invoke_script(
    repo: Path,
    *,
    pr_body: str | None = None,
    base: str = "HEAD~1",
    head: str = "HEAD",
) -> subprocess.CompletedProcess[str]:
    args: list[str] = [
        sys.executable,
        str(SCRIPT_PATH),
        "--base",
        base,
        "--head",
        head,
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

TOML_MULTI = textwrap.dedent(
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


# --- Happy-path ---


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


# --- Failure inputs ---


def test_loosening_without_justification_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen without reason")
    proc = _invoke_script(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "BLOCK" in proc.stdout
    assert "a_pass_rate" in proc.stdout


def test_sentinel_names_wrong_threshold_blocks(tmp_path: Path) -> None:
    """S5U-643: naming the wrong threshold does not cover the actual loosening.

    Red-before confirmation: ran against
    `/tmp/s5u-643-redbefore/check_threshold_changes_baseline.py` — the pre-fix
    scanner accepted ANY `LOOSEN-THRESHOLD: <reason>` line, regardless of
    threshold name. Output: exit 0, "Justification found in commit message:
    overall_pass_rate — wrong name". Post-fix: exit 1, "a_pass_rate ... has
    no 'LOOSEN-THRESHOLD: a_pass_rate ...' sentinel".
    """
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(
        repo,
        loosened,
        message="loosen\n\nLOOSEN-THRESHOLD: overall_pass_rate — wrong name",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "BLOCK" in proc.stdout


def test_empty_reason_sentinel_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.80")
    _make_head_commit(repo, loosened, message="loosen\n\nLOOSEN-THRESHOLD: a_pass_rate —")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "BLOCK" in proc.stdout


# --- Adversarial: the exploit S5U-643 closes ---


def test_decoy_sentinel_on_unrelated_commit_blocks(tmp_path: Path) -> None:
    """S5U-643 EXPLOIT: decoy sentinel on commit A, silent loosen on commit B.

    Exact attack from the Linear issue. Pre-fix (baseline at `cbd0256`):
    scanner aggregated `LOOSEN-THRESHOLD:` lines across all commits that
    touched thresholds.toml → commit A's decoy covered commit B → exit 0.

    Red-before confirmation: commit cbd0256 scripts/check_threshold_changes.py
    shows this scenario passes because `has_commit_sentinel` (pre-fix) only
    needs one sentinel anywhere in `base..head`. Post-fix: exit 1 because
    the responsible commit for `b_pass_rate` is commit B, whose message
    contains no sentinel naming `b_pass_rate`.
    """
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    # Commit A: add a trailing comment to TOML but do NOT change any values.
    commit_a_toml = TOML_MULTI + "\n# harmless comment\n"
    _make_head_commit(
        repo,
        commit_a_toml,
        message="prep\n\nLOOSEN-THRESHOLD: a_pass_rate — placeholder excuse",
    )
    # Commit B: silently lower b_pass_rate with no sentinel.
    commit_b_toml = commit_a_toml.replace("min = 0.90", "min = 0.50")
    _make_head_commit(repo, commit_b_toml, message="unrelated tweak")

    # Invoke with base pointing to the commit before A.
    proc = _invoke_script(repo, base="HEAD~2", head="HEAD")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "BLOCK" in proc.stdout
    assert "b_pass_rate" in proc.stdout


def test_decoy_sentinel_on_commit_a_doesnt_cover_loosening_in_commit_b(
    tmp_path: Path,
) -> None:
    """S5U-643: even if commit A has a VALID named sentinel for threshold X,
    it does NOT cover threshold Y silently loosened in commit B.
    """
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    # Commit A lowers a_pass_rate legitimately with a proper named sentinel.
    commit_a_toml = TOML_MULTI.replace("min = 0.98", "min = 0.80")
    _make_head_commit(
        repo,
        commit_a_toml,
        message="loosen a\n\nLOOSEN-THRESHOLD: a_pass_rate — audit linked",
    )
    # Commit B silently lowers b_pass_rate with NO sentinel.
    commit_b_toml = commit_a_toml.replace("min = 0.90", "min = 0.50")
    _make_head_commit(repo, commit_b_toml, message="side tweak")

    proc = _invoke_script(repo, base="HEAD~2", head="HEAD")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "b_pass_rate" in proc.stdout
    # a_pass_rate WAS covered, so it should be reported as justified.
    assert "a_pass_rate: justified by commit" in proc.stdout


def test_multi_threshold_sentinel_covers_all_in_one_commit(tmp_path: Path) -> None:
    """S5U-643: `LOOSEN-THRESHOLD: a, b — reason` covers both."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    both_loosened = TOML_MULTI.replace("min = 0.98", "min = 0.80").replace(
        "min = 0.90", "min = 0.50"
    )
    _make_head_commit(
        repo,
        both_loosened,
        message=(
            "joint recalibration\n\n"
            "LOOSEN-THRESHOLD: a_pass_rate, b_pass_rate — both metrics rebaselined"
        ),
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_multi_threshold_sentinel_partial_coverage_blocks(tmp_path: Path) -> None:
    """S5U-643: if sentinel names only one of two loosened thresholds, block."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    both_loosened = TOML_MULTI.replace("min = 0.98", "min = 0.80").replace(
        "min = 0.90", "min = 0.50"
    )
    _make_head_commit(
        repo,
        both_loosened,
        message="partial\n\nLOOSEN-THRESHOLD: a_pass_rate — only A is justified",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "b_pass_rate" in proc.stdout
    assert "BLOCK" in proc.stdout


def test_pr_body_partial_coverage_blocks(tmp_path: Path) -> None:
    """S5U-643: PR body must cover EVERY loosening, not just some."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    both_loosened = TOML_MULTI.replace("min = 0.98", "min = 0.80").replace(
        "min = 0.90", "min = 0.50"
    )
    _make_head_commit(repo, both_loosened, message="no sentinels")
    pr_body = (
        "## Threshold loosening justification\n\n"
        "- a_pass_rate: see audit\n"
        "(missing b_pass_rate bullet)\n"
    )
    proc = _invoke_script(repo, pr_body=pr_body)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "b_pass_rate" in proc.stdout
    assert "BLOCK" in proc.stdout


def test_pr_body_covers_all_loosenings_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    both_loosened = TOML_MULTI.replace("min = 0.98", "min = 0.80").replace(
        "min = 0.90", "min = 0.50"
    )
    _make_head_commit(repo, both_loosened, message="no sentinels")
    pr_body = (
        "## Threshold loosening justification\n\n"
        "- a_pass_rate: audit report linked\n"
        "- b_pass_rate: dataset drift mean 0.82\n"
    )
    proc = _invoke_script(repo, pr_body=pr_body)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_mixed_justification_commit_and_pr_body_passes(tmp_path: Path) -> None:
    """S5U-643: finding A justified by commit sentinel, finding B by PR body — both ok."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_MULTI)
    # Commit A loosens a with named sentinel.
    a_only = TOML_MULTI.replace("min = 0.98", "min = 0.80")
    _make_head_commit(
        repo,
        a_only,
        message="loosen a\n\nLOOSEN-THRESHOLD: a_pass_rate — audit linked",
    )
    # Commit B loosens b but has no sentinel; PR body will cover it.
    a_and_b = a_only.replace("min = 0.90", "min = 0.50")
    _make_head_commit(repo, a_and_b, message="loosen b")
    pr_body = (
        "## Threshold loosening justification\n\n- b_pass_rate: dataset drift, mean moved to 0.52\n"
    )
    proc = _invoke_script(repo, pr_body=pr_body, base="HEAD~2", head="HEAD")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_deletion_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    _make_head_commit(repo, "version = 1\n", message="delete a_pass_rate")
    proc = _invoke_script(repo)
    assert proc.returncode == 1
    assert "deleted" in proc.stdout


def test_deletion_with_named_sentinel_passes(tmp_path: Path) -> None:
    """S5U-643: deletion is a loosening; sentinel must name the deleted threshold."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    _make_head_commit(
        repo,
        "version = 1\n",
        message="retire\n\nLOOSEN-THRESHOLD: a_pass_rate — metric retired per S5U-XXX",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_blocking_flip_with_named_sentinel_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    flipped = TOML_SIMPLE.replace("blocking = true", "blocking = false")
    _make_head_commit(
        repo,
        flipped,
        message="advisory\n\nLOOSEN-THRESHOLD: a_pass_rate — advisory-only pending dataset refresh",
    )
    proc = _invoke_script(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_missing_base_ref_hard_errors(tmp_path: Path) -> None:
    """S5U-642: unresolvable base ref must fail closed (regression guard)."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    loosened = TOML_SIMPLE.replace("min = 0.98", "min = 0.50")
    _make_head_commit(repo, loosened, message="loosen")
    proc = _invoke_script(repo, base="origin/nonexistent_base")
    assert proc.returncode != 0
    combined = (proc.stdout + proc.stderr).lower()
    assert "cannot resolve ref" in combined or "fetch-depth" in combined


def test_missing_head_ref_hard_errors(tmp_path: Path) -> None:
    """S5U-642: unresolvable head ref also hard-errors (symmetry)."""
    repo = tmp_path / "repo"
    _init_repo_with_base(repo, TOML_SIMPLE)
    proc = _invoke_script(repo, base="HEAD", head="nonexistent_head_ref")
    assert proc.returncode != 0
    assert "cannot resolve ref" in (proc.stdout + proc.stderr).lower()

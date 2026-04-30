"""End-to-end failure / adversarial / wire tests for scripts/check_threshold_changes.py.

S5U-656 split-out from the original test_check_threshold_changes.py:
failure-input, adversarial-decoy, multi-threshold, deletion, blocking-flip,
and missing-ref tests live here. The happy-path E2E tests live in
test_check_threshold_changes_e2e_happy.py. Shared helpers
(git repo setup, subprocess invocation, TOML constants) live in
_threshold_test_helpers.py.

S5U-643 per-finding tests carry red-before evidence pointing at the
pre-fix baseline at SHA `cbd0256` — see the docstrings on individual
adversarial tests for details.
"""

from __future__ import annotations

from pathlib import Path

from ._threshold_test_helpers import (
    TOML_MULTI,
    TOML_SIMPLE,
    _init_repo_with_base,
    _invoke_script,
    _make_head_commit,
)

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

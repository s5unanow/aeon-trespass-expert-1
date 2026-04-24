"""Unit tests for scripts/check_post_merge_coordinator_ack.py (S5U-693).

Covers the regex (G2 — content-derived set), G1 degenerate-input fail-closed
cases, and the find_valid_coordinator_ack selection logic. End-to-end
audit() flow tests live in `test_check_post_merge_coordinator_ack_audit.py`.

Red-before anchor: the script was authored with the audit() function as the
last body to fill in. Running these tests against a stub that returns 1 on
every path produces 1 failure (the no-safety-gate happy-path expecting exit 0).
The non-unit/audit tests here are G1 fail-closed and regex coverage — they
PASS under the stub AND under the real implementation, because both assert
RuntimeError is raised or the regex matches. The red-before evidence for this
file's tests is the stub-driven failure of the audit happy-path test in the
companion file (documented in tmp/plan-s5u-693.md §5b).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _run_git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)


def _init_repo(root: Path) -> tuple[str, str]:
    _run_git(["git", "init", "-b", "main"], root)
    _run_git(["git", "config", "user.email", "test@example.com"], root)
    _run_git(["git", "config", "user.name", "Test"], root)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(["git", "add", "README.md"], root)
    _run_git(["git", "commit", "-m", "base"], root)
    base = _run_git(["git", "rev-parse", "HEAD"], root).stdout.strip()
    return base, base


# ---------------------------------------------------------------------------
# Safety-gate regex coverage (G2 — content-derived set)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        ".github/workflows/new.yml",
        ".github/actions/composite/action.yml",
        ".claude/hooks/pre-pr-check.sh",
        ".claude/prompts/review.md",
        ".claude/prompts/codex-review.md",
        ".claude/coordinator-signers.txt",
        ".claude/skills/ship/SKILL.md",
        "scripts/check_foo.py",
        "scripts/check_bar.sh",
        "scripts/pre-ship.py",
        "scripts/test_pre_pr_safety_gate.sh",
    ],
)
def test_safety_gate_regex_matches_all_in_scope_paths(mod: ModuleType, path: str) -> None:
    """G2: every documented safety-gate surface matches by path shape."""
    hits = mod.safety_gate_hits([path])
    assert hits == [path], f"expected {path!r} to match safety-gate regex"


@pytest.mark.parametrize(
    "path",
    [
        "apps/web/src/foo.ts",
        "apps/pipeline/src/bar.py",
        "docs/README.md",
        "configs/base.toml",
        "scripts/export_to_web.py",  # scripts/<not check_/pre-/test_...> → not in scope
        "README.md",  # top-level README is not CLAUDE.md
    ],
)
def test_safety_gate_regex_does_not_match_out_of_scope_paths(mod: ModuleType, path: str) -> None:
    """G2: non-safety-gate paths are correctly excluded."""
    assert mod.safety_gate_hits([path]) == []


def test_safety_gate_regex_matches_renamed_script(mod: ModuleType) -> None:
    """G2: renaming within the path pattern still matches (not a name-list)."""
    hits = mod.safety_gate_hits(
        ["scripts/check_make_doc_parity.py", "scripts/check_makefile_doc_parity.py"]
    )
    assert set(hits) == {
        "scripts/check_make_doc_parity.py",
        "scripts/check_makefile_doc_parity.py",
    }


# ---------------------------------------------------------------------------
# G1: fail-closed defaults
# ---------------------------------------------------------------------------


def test_missing_base_or_head_fails_closed(mod: ModuleType, tmp_path: Path) -> None:
    """G1: absent base/head SHAs exit with a clear message."""
    with pytest.raises(RuntimeError, match="needs both base and head SHAs"):
        mod.diff_paths("", "abc", tmp_path)
    with pytest.raises(RuntimeError, match="needs both base and head SHAs"):
        mod.diff_paths("abc", "", tmp_path)


def test_unresolvable_base_ref_fails_closed(mod: ModuleType, tmp_path: Path) -> None:
    """G1: shallow-checkout / missing ref fails closed with shallow-checkout hint."""
    base, _ = _init_repo(tmp_path)
    with pytest.raises(RuntimeError, match="does not resolve"):
        mod.diff_paths("deadbeef0000000000000000000000000000dead", base, tmp_path)


def test_missing_allowlist_fails_closed(mod: ModuleType, tmp_path: Path) -> None:
    """G1: missing .claude/coordinator-signers.txt exits non-zero."""
    with pytest.raises(RuntimeError, match=r"allowlist file .* is missing"):
        mod.load_allowlist(tmp_path)


def test_empty_allowlist_fails_closed(mod: ModuleType, tmp_path: Path) -> None:
    """G1: allowlist file with only comments/blanks fails closed."""
    path = tmp_path / ".claude" / "coordinator-signers.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# comment only\n\n  \n# another\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="has no signers"):
        mod.load_allowlist(tmp_path)


def test_malformed_status_json_fails_closed(mod: ModuleType) -> None:
    """G1: non-JSON response from gh api fails closed."""
    with (
        patch.object(mod, "_gh_api", return_value="not-json"),
        pytest.raises(RuntimeError, match="not valid JSON"),
    ):
        mod.fetch_statuses("owner/repo", "abc")


def test_status_json_not_array_fails_closed(mod: ModuleType) -> None:
    """G1: if /commits/<sha>/statuses returns an object instead of array, fail closed."""
    with (
        patch.object(mod, "_gh_api", return_value='{"message": "Not Found"}'),
        pytest.raises(RuntimeError, match="not a JSON array"),
    ):
        mod.fetch_statuses("owner/repo", "abc")


def test_gh_missing_fails_closed(mod: ModuleType) -> None:
    """G1: absent gh CLI fails closed with a hint."""

    def _raise(*a: Any, **kw: Any) -> Any:
        raise FileNotFoundError("gh not found")

    with (
        patch.object(subprocess, "run", side_effect=_raise),
        pytest.raises(RuntimeError, match="'gh' CLI not found"),
    ):
        mod._gh_api("foo")


def test_gh_nonzero_fails_closed(mod: ModuleType) -> None:
    """G1: gh api non-zero exit fails closed with stderr."""
    fake = MagicMock()
    fake.returncode = 1
    fake.stderr = "API rate limit exceeded"
    fake.stdout = ""
    with (
        patch.object(subprocess, "run", return_value=fake),
        pytest.raises(RuntimeError, match="API rate limit"),
    ):
        mod._gh_api("foo")


def test_main_missing_repo_fails_closed(mod: ModuleType) -> None:
    """G1: main() with no --repo and empty GITHUB_REPOSITORY returns 1."""
    # Clear env to simulate absence.
    with patch.dict("os.environ", {"GITHUB_REPOSITORY": ""}, clear=False):
        rc = mod.main(["--base", "abc", "--head", "def"])
    assert rc == 1


# ---------------------------------------------------------------------------
# Coordinator-ack selection logic
# ---------------------------------------------------------------------------


def test_find_valid_coordinator_ack_empty(mod: ModuleType) -> None:
    """Empty status list → no ack."""
    assert mod.find_valid_coordinator_ack([], ["s5unanow"]) is None


def test_find_valid_coordinator_ack_non_allowlisted(mod: ModuleType) -> None:
    """Status posted by non-allowlisted login is rejected (forgery guard)."""
    s = mod.StatusEntry(
        context="coordinator-ack",
        state="success",
        creator_login="attacker",
        created_at="2026-04-21T12:00:00Z",
    )
    assert mod.find_valid_coordinator_ack([s], ["s5unanow"]) is None


def test_find_valid_coordinator_ack_later_failure_revokes(mod: ModuleType) -> None:
    """Latest status is failure → revoked; prior success does NOT count.

    Matches the jq `sort_by(.created_at) | .[-1]` rule from pre-pr-check.sh
    (S5U-673): a later failure revokes a prior success.
    """
    ok = mod.StatusEntry(
        context="coordinator-ack",
        state="success",
        creator_login="s5unanow",
        created_at="2026-04-21T12:00:00Z",
    )
    revoked = mod.StatusEntry(
        context="coordinator-ack",
        state="failure",
        creator_login="s5unanow",
        created_at="2026-04-21T13:00:00Z",
    )
    assert mod.find_valid_coordinator_ack([ok, revoked], ["s5unanow"]) is None


def test_find_valid_coordinator_ack_happy_path(mod: ModuleType) -> None:
    """Latest coordinator-ack is success AND allowlisted → valid."""
    s = mod.StatusEntry(
        context="coordinator-ack",
        state="success",
        creator_login="s5unanow",
        created_at="2026-04-21T12:00:00Z",
    )
    assert mod.find_valid_coordinator_ack([s], ["s5unanow"]) is s

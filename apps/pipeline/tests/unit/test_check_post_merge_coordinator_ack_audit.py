"""End-to-end audit() flow tests for check_post_merge_coordinator_ack (S5U-693).

These are the tests whose red-before anchor is the stub variant described in
tmp/plan-s5u-693.md §5b. Running them against an audit() stub that always
returns 1 makes `test_audit_no_safety_gate_diff_passes` fail
(expected 0, got 1). Running them against the real implementation exercises
every branch of the audit: safety-gate match, allowlist load, status lookup
on the merge commit SHA, status lookup on the associated PR HEAD SHA, and
the latest-status-wins revocation semantics.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


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


def _commit(root: Path, rel: str, content: str, msg: str) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _run_git(["git", "add", rel], root)
    _run_git(["git", "commit", "-m", msg], root)
    return _run_git(["git", "rev-parse", "HEAD"], root).stdout.strip()


def _write_allowlist(root: Path, logins: list[str]) -> None:
    path = root / ".claude" / "coordinator-signers.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "# comment\n\n" + "\n".join(logins) + "\n"
    path.write_text(body, encoding="utf-8")


def test_audit_no_safety_gate_diff_passes(mod: ModuleType, tmp_path: Path) -> None:
    """Happy path: non-safety-gate diff → exit 0 (silent)."""
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "apps/web/src/foo.ts", "ok\n", "web edit")
    rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 0


def test_audit_safety_gate_diff_without_ack_fails(mod: ModuleType, tmp_path: Path) -> None:
    """Failure path: safety-gate diff, no coordinator-ack anywhere → exit 1."""
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "claude edit")
    _write_allowlist(tmp_path, ["s5unanow"])

    # Stub gh api to return empty statuses AND empty PRs.
    def _fake_gh(path: str) -> str:
        if "/statuses" in path:
            return "[]"
        if "/pulls" in path:
            return "[]"
        return "{}"

    with patch.object(mod, "_gh_api", side_effect=_fake_gh):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 1


def test_audit_safety_gate_diff_with_valid_ack_on_head_passes(
    mod: ModuleType, tmp_path: Path
) -> None:
    """Happy path: safety-gate diff AND coordinator-ack on merge commit → exit 0."""
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "claude edit")
    _write_allowlist(tmp_path, ["s5unanow"])

    statuses_response = json.dumps(
        [
            {
                "context": "coordinator-ack",
                "state": "success",
                "creator": {"login": "s5unanow"},
                "created_at": "2026-04-21T12:00:00Z",
            }
        ]
    )

    def _fake_gh(path: str) -> str:
        if path.endswith(f"/commits/{head}/statuses"):
            return statuses_response
        if "/statuses" in path:
            return "[]"
        if "/pulls" in path:
            return "[]"
        return "{}"

    with patch.object(mod, "_gh_api", side_effect=_fake_gh):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 0


def test_audit_ack_on_associated_pr_head_passes(mod: ModuleType, tmp_path: Path) -> None:
    """Squash-merge path: ack is on the PR HEAD SHA, not the merge SHA.

    The audit must follow `/commits/<merge>/pulls` to find the PR, then
    check statuses on the PR HEAD SHA.
    """
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "squash merge")
    _write_allowlist(tmp_path, ["s5unanow"])

    pr_head_sha = "ffff" + "0" * 36  # a hypothetical pre-squash PR HEAD
    statuses_on_pr_head = json.dumps(
        [
            {
                "context": "coordinator-ack",
                "state": "success",
                "creator": {"login": "s5unanow"},
                "created_at": "2026-04-21T12:00:00Z",
            }
        ]
    )

    def _fake_gh(path: str) -> str:
        if path.endswith(f"/commits/{pr_head_sha}/statuses"):
            return statuses_on_pr_head
        if "/statuses" in path:
            return "[]"
        if path.endswith(f"/commits/{head}/pulls"):
            return json.dumps([{"number": 307}])
        if path.endswith("/pulls/307"):
            return json.dumps({"head": {"sha": pr_head_sha}})
        if "/pulls" in path:
            return "[]"
        return "{}"

    with patch.object(mod, "_gh_api", side_effect=_fake_gh):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 0


def test_audit_ack_from_non_allowlisted_signer_fails(mod: ModuleType, tmp_path: Path) -> None:
    """Adversarial: worker self-posts 'coordinator-ack' under own login → rejected.

    The forgery guard is the allowlist check. GitHub stamps creator.login from
    the OAuth token; a worker cannot mint a status under a foreign login.
    """
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "claude edit")
    _write_allowlist(tmp_path, ["s5unanow"])

    statuses_response = json.dumps(
        [
            {
                "context": "coordinator-ack",
                "state": "success",
                "creator": {"login": "attacker-worker"},
                "created_at": "2026-04-21T12:00:00Z",
            }
        ]
    )

    def _fake_gh(path: str) -> str:
        if "/statuses" in path:
            return statuses_response
        if "/pulls" in path:
            return "[]"
        return "{}"

    with patch.object(mod, "_gh_api", side_effect=_fake_gh):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 1


def test_audit_recovers_from_pulls_propagation_delay(mod: ModuleType, tmp_path: Path) -> None:
    """S5U-728 regression: first /pulls call returns [], retry returns the PR.

    Reproduces the PR #320 / S5U-694 false-negative where the audit ran ~0.9s
    after merge and the GitHub commit→PR association index had not yet caught
    up. With retry-with-backoff in fetch_pull_numbers_for_commit, the second
    or later attempt finds the PR; the audit then resolves the PR HEAD SHA
    and verifies the coordinator-ack on it.
    """
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "squash merge")
    _write_allowlist(tmp_path, ["s5unanow"])

    pr_head_sha = "8426" + "8" * 36
    statuses_on_pr_head = json.dumps(
        [
            {
                "context": "coordinator-ack",
                "state": "success",
                "creator": {"login": "s5unanow"},
                "created_at": "2026-04-21T12:00:00Z",
            }
        ]
    )

    pulls_responses_for_head = iter(["[]", json.dumps([{"number": 320}])])

    def _fake_gh(path: str) -> str:
        if path.endswith(f"/commits/{pr_head_sha}/statuses"):
            return statuses_on_pr_head
        if "/statuses" in path:
            return "[]"
        if path.endswith(f"/commits/{head}/pulls"):
            # First call mimics the propagation delay; second succeeds.
            return next(pulls_responses_for_head)
        if path.endswith("/pulls/320"):
            return json.dumps({"head": {"sha": pr_head_sha}})
        if "/pulls" in path:
            return "[]"
        return "{}"

    sleeps: list[float] = []
    # The conftest `mod` fixture already rebinds `mod.time` so real sleeps
    # never fire (S5U-728); here we additionally observe that at least one
    # backoff sleep happens by patching the rebound stand-in's `sleep`.
    with (
        patch.object(mod, "_gh_api", side_effect=_fake_gh),
        patch.object(mod.time, "sleep", side_effect=sleeps.append),
    ):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)

    assert rc == 0, "audit must recover from /pulls propagation delay"
    # We expect exactly one backoff sleep (between attempt 1 and 2).
    assert len(sleeps) >= 1, "retry path must invoke sleeper at least once"


def test_audit_ack_with_later_failure_is_revoked(mod: ModuleType, tmp_path: Path) -> None:
    """Adversarial: a later failure status revokes a prior success (S5U-673 parity)."""
    base, _ = _init_repo(tmp_path)
    head = _commit(tmp_path, "CLAUDE.md", "changed\n", "claude edit")
    _write_allowlist(tmp_path, ["s5unanow"])

    statuses_response = json.dumps(
        [
            {
                "context": "coordinator-ack",
                "state": "success",
                "creator": {"login": "s5unanow"},
                "created_at": "2026-04-21T12:00:00Z",
            },
            {
                "context": "coordinator-ack",
                "state": "failure",
                "creator": {"login": "s5unanow"},
                "created_at": "2026-04-21T13:00:00Z",
            },
        ]
    )

    def _fake_gh(path: str) -> str:
        if "/statuses" in path:
            return statuses_response
        if "/pulls" in path:
            return "[]"
        return "{}"

    with patch.object(mod, "_gh_api", side_effect=_fake_gh):
        rc = mod.audit(repo="owner/repo", base=base, head=head, root=tmp_path)
    assert rc == 1

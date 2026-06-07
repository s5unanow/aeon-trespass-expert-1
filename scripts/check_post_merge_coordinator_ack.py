#!/usr/bin/env python3
"""Post-merge coordinator-ack audit (S5U-693).

Runs on every push to `main` via `.github/workflows/post-merge-coordinator-ack.yml`.
If the merged push touches safety-gate scope (the name-derived regex below plus
the content-derived corpus `detector_sources` union, S5U-922 — kept in sync with
`.claude/hooks/pre-pr-check.sh`), the script queries the GitHub API for a
`coordinator-ack` commit status on the PR HEAD SHA and fails the workflow when no
valid ack exists. This is an audit-trail gate, not a merge gate — branch
protection only applies at PR time. A red run is a durable signal that
complements the pre-PR hook (which only intercepts local `gh pr create`).

Per `.claude/rules/guards.md` Rule G1, every degenerate input exits non-zero:
missing/unresolvable base ref, `git diff` failure, `gh api` non-zero, malformed
JSON, missing/empty allowlist, malformed corpus. Per Rule G2, scope is
path-regex + content-derived corpus union (not a hardcoded name list).

Usage:
    python scripts/check_post_merge_coordinator_ack.py \\
        --repo <owner>/<repo> --base <sha> --head <sha>

`--base` and `--head` default to `GITHUB_EVENT_BEFORE` and `GITHUB_SHA` env
vars when omitted, so the workflow invocation is bare.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Shared content-derived detector-source scope helper (S5U-922).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _detector_source_scope import DetectorScopeError, detector_source_scope

REPO_ROOT = Path(__file__).resolve().parents[1]

# Safety-gate scope regex (NAME-DERIVED) — MUST match the grep in
# .claude/hooks/pre-pr-check.sh verbatim. CONTENT-DERIVED corpus detector_sources
# are unioned on top in `safety_gate_hits` (S5U-922).
SAFETY_GATE_REGEX = re.compile(
    r"^("
    r"\.claude/hooks/|"
    r"\.claude/prompts/review\.md$|"
    r"\.claude/prompts/codex-review\.md$|"
    r"\.claude/coordinator-signers\.txt$|"
    r"\.github/workflows/|"
    r"\.github/actions/|"
    r"\.claude/skills/.+/SKILL\.md$|"
    r"scripts/check_[^/]+\.(sh|py)$|"
    r"scripts/pre-[^/]+\.(sh|py)$|"
    r"scripts/test_pre_pr_safety_gate\.sh$|"
    r"scripts/_detector_source_scope\.py$|"
    r"CLAUDE\.md$"
    r")"
)

ALLOWLIST_FILE = Path(".claude/coordinator-signers.txt")


@dataclass(frozen=True)
class StatusEntry:
    """A single GitHub commit status relevant to coordinator-ack."""

    context: str
    state: str
    creator_login: str
    created_at: str


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command. Fail closed on non-zero exit (G1)."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"BLOCKED: git {' '.join(args)} failed (exit {result.returncode}).\n"
            f"  stderr: {result.stderr.strip()}\n"
            "Per .claude/rules/guards.md Rule G1, git failures fail closed."
        )
    return result.stdout


def diff_paths(base: str, head: str, cwd: Path) -> list[str]:
    """Return paths changed between base..head. Fail closed on git failure."""
    if not base or not head:
        raise RuntimeError(
            "BLOCKED: post-merge-coordinator-ack needs both base and head SHAs.\n"
            "  Pass --base and --head explicitly, or set GITHUB_EVENT_BEFORE\n"
            "  and GITHUB_SHA in the workflow env.\n"
            "Per .claude/rules/guards.md Rule G1, missing input fails closed."
        )
    # Verify both refs resolve — a shallow checkout produces non-existent refs.
    for ref in (base, head):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            raise RuntimeError(
                f"BLOCKED: ref '{ref}' does not resolve in this working tree.\n"
                "  This usually means a shallow checkout; re-run with\n"
                "  fetch-depth: 0 on actions/checkout.\n"
                "Per .claude/rules/guards.md Rule G1, missing refs fail closed."
            )
    out = _run_git(["diff", "--name-only", f"{base}..{head}"], cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def safety_gate_hits(paths: list[str], *, root: Path = REPO_ROOT) -> list[str]:
    """Filter paths to the safety-gate subset (S5U-922 content-derived union).

    In scope = matches ``SAFETY_GATE_REGEX`` (name-derived) OR is a declared
    corpus ``detector_sources`` entry. Malformed corpus → ``RuntimeError`` (G1).
    """
    try:
        scope = detector_source_scope(repo_root=root)
    except DetectorScopeError as exc:
        raise RuntimeError(
            f"BLOCKED: cannot compute detector-source safety-gate scope: {exc}"
        ) from exc
    return [p for p in paths if SAFETY_GATE_REGEX.match(p) or p in scope]


def load_allowlist(root: Path) -> list[str]:
    """Load `.claude/coordinator-signers.txt`. Fail closed on missing/empty (G1)."""
    path = root / ALLOWLIST_FILE
    if not path.exists():
        raise RuntimeError(
            f"BLOCKED: allowlist file '{ALLOWLIST_FILE}' is missing.\n"
            "Per .claude/rules/guards.md Rule G1, fail closed."
        )
    logins: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # First whitespace-delimited token (matches the shell parser).
        logins.append(stripped.split()[0])
    if not logins:
        raise RuntimeError(
            f"BLOCKED: allowlist file '{ALLOWLIST_FILE}' has no signers.\n"
            "Per .claude/rules/guards.md Rule G1, empty allowlist fails closed."
        )
    return logins


def _gh_api(path: str) -> str:
    """Invoke `gh api <path>`. Fail closed on missing gh or non-zero exit."""
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "BLOCKED: 'gh' CLI not found; cannot query GitHub API.\n"
            "Per .claude/rules/guards.md Rule G1, fail closed."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"BLOCKED: gh api {path} failed (exit {result.returncode}).\n"
            f"  stderr: {result.stderr.strip()}\n"
            "Per .claude/rules/guards.md Rule G1, API failures fail closed."
        )
    return result.stdout


def fetch_statuses(repo: str, sha: str) -> list[StatusEntry]:
    """Fetch commit statuses. Fail closed on malformed JSON (G1)."""
    raw = _gh_api(f"repos/{repo}/commits/{sha}/statuses")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"BLOCKED: status response for {sha} is not valid JSON.\n"
            f"  parse error: {exc}\n"
            "Per .claude/rules/guards.md Rule G1, parse errors fail closed."
        ) from exc
    if not isinstance(data, list):
        raise RuntimeError(
            f"BLOCKED: status response for {sha} is not a JSON array.\n"
            "Per .claude/rules/guards.md Rule G1, fail closed on bad shape."
        )
    out: list[StatusEntry] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        creator = item.get("creator") or {}
        out.append(
            StatusEntry(
                context=str(item.get("context", "")),
                state=str(item.get("state", "")),
                creator_login=str(creator.get("login", "")) if isinstance(creator, dict) else "",
                created_at=str(item.get("created_at", "")),
            )
        )
    return out


def _parse_pull_numbers(raw: str) -> list[int]:
    """Parse /commits/<sha>/pulls JSON into PR numbers; [] on any malformed shape.

    The caller treats empty as "no PRs found this attempt" and either retries or
    falls back to the merge-commit-SHA status check. The pass/fail-deciding
    `/statuses` endpoint is NOT this permissive — `fetch_statuses` fails closed.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    numbers: list[int] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        num = item.get("number")
        if isinstance(num, int):
            numbers.append(num)
    return numbers


def fetch_pull_numbers_for_commit(
    repo: str,
    sha: str,
    *,
    max_retries: int = 5,
    initial_backoff_s: float = 2.0,
    sleeper: Callable[[float], None] | None = None,
) -> list[int]:
    """Find PR numbers whose merge commit equals sha, with retry-with-backoff.

    GitHub's `/commits/<sha>/pulls` is eventually consistent after a squash merge
    (S5U-728: PR #320 audit ran ~0.9s after merge and got `[]` despite a valid
    PR-HEAD ack). Exponential backoff lets the index settle. Empty `[]` AND
    transient `RuntimeError` from `_gh_api` are both retried; returning `[]` after
    the budget preserves the legitimate force-push / direct-push pathway. The
    pass/fail decision happens in `fetch_statuses`, which fails closed (G1).
    `sleeper` is parameterized for tests and resolved at call time so patches on
    `mod.time.sleep` work (default-arg binding would bypass the patch).
    """
    if max_retries < 1:
        # Defensive: never silently degrade to zero attempts.
        max_retries = 1
    sleep_fn: Callable[[float], None] = sleeper if sleeper is not None else time.sleep
    for attempt in range(max_retries):
        try:
            raw = _gh_api(f"repos/{repo}/commits/{sha}/pulls")
            numbers = _parse_pull_numbers(raw)
            if numbers:
                return numbers
        except RuntimeError:
            # Transient gh failure — same handling as empty: retry until budget.
            pass
        if attempt < max_retries - 1:
            sleep_fn(initial_backoff_s * (2**attempt))
    return []


def fetch_pr_head_sha(repo: str, number: int) -> str | None:
    """Return the PR HEAD SHA, or None on failure."""
    try:
        raw = _gh_api(f"repos/{repo}/pulls/{number}")
    except RuntimeError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    head = data.get("head") or {}
    if isinstance(head, dict):
        sha = head.get("sha")
        if isinstance(sha, str):
            return sha
    return None


def find_valid_coordinator_ack(
    statuses: list[StatusEntry], allowlist: list[str]
) -> StatusEntry | None:
    """Return latest-by-created_at success coordinator-ack from an allowlisted signer.

    Mirrors `pre-pr-check.sh` (S5U-673) latest-wins: a later failure revokes
    a prior success; only the latest entry is consulted.
    """
    ack = [s for s in statuses if s.context == "coordinator-ack"]
    if not ack:
        return None
    latest = sorted(ack, key=lambda s: s.created_at)[-1]
    if latest.state != "success" or latest.creator_login not in allowlist:
        return None
    return latest


def audit(*, repo: str, base: str, head: str, root: Path) -> int:
    """Core audit logic. Returns exit code (0 = pass, 1 = fail)."""
    paths = diff_paths(base, head, root)
    hits = safety_gate_hits(paths)
    if not hits:
        print(f"No safety-gate paths in push range {base[:7]}..{head[:7]}; skipping.")
        return 0

    print("Safety-gate paths in merged push range:")
    for path_hit in hits:
        print(f"  {path_hit}")

    allowlist = load_allowlist(root)
    print(f"Coordinator signer allowlist: {', '.join(allowlist)}")

    # SHAs to check: merge commit + push-range commits, plus PR HEAD SHAs
    # discovered via /commits/<sha>/pulls.
    commits_to_check: set[str] = {head}
    range_out = _run_git(["rev-list", f"{base}..{head}"], root)
    for line in range_out.splitlines():
        sha = line.strip()
        if sha:
            commits_to_check.add(sha)
    pr_numbers: set[int] = set()
    for sha in list(commits_to_check):
        for num in fetch_pull_numbers_for_commit(repo, sha):
            pr_numbers.add(num)
    for num in pr_numbers:
        pr_head = fetch_pr_head_sha(repo, num)
        if pr_head:
            commits_to_check.add(pr_head)
    print(f"Checking {len(commits_to_check)} commit(s) for coordinator-ack status.")

    for sha in sorted(commits_to_check):
        statuses = fetch_statuses(repo, sha)
        valid = find_valid_coordinator_ack(statuses, allowlist)
        if valid is not None:
            print(
                f"Coordinator-ack verified on {sha[:7]}: "
                f"state=success, creator={valid.creator_login}, "
                f"created_at={valid.created_at}"
            )
            return 0

    # No valid coordinator-ack anywhere. Fail closed.
    pr_list = ", ".join(str(n) for n in sorted(pr_numbers)) or "<none>"
    print(
        "BLOCKED: no valid coordinator-ack commit status found for the "
        "safety-gate-scope change in this push.\n"
        f"  Checked commits: {', '.join(sorted(s[:7] for s in commits_to_check))}\n"
        f"  Associated PRs:  {pr_list}\n"
        "\n"
        "Per CLAUDE.md step 6 and the S5U-693 post-merge audit rule, any "
        "safety-gate-scope merge must have a 'coordinator-ack' commit status "
        "(state=success) from an allowlisted signer on the PR HEAD SHA at "
        "merge time. This workflow complements the pre-PR hook (which only "
        "intercepts local `gh pr create`)."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Reads env var fallbacks for workflow convenience."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--base", default=os.environ.get("GITHUB_EVENT_BEFORE", ""))
    parser.add_argument("--head", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if not args.repo:
        print(
            "BLOCKED: --repo not provided and GITHUB_REPOSITORY env var is empty.\n"
            "Per .claude/rules/guards.md Rule G1, fail closed."
        )
        return 1

    try:
        return audit(repo=args.repo, base=args.base, head=args.head, root=args.repo_root)
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

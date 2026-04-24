#!/usr/bin/env python3
"""Post-merge coordinator-ack audit (S5U-693).

Runs on every push to `main` via `.github/workflows/post-merge-coordinator-ack.yml`.
If the push contains commits whose combined diff touches safety-gate scope (per
the regex in `.claude/hooks/pre-pr-check.sh` line 224), the script queries the
GitHub API for a `coordinator-ack` commit status on the PR HEAD SHA and fails
the workflow when no valid ack exists.

This is an **audit-trail** gate, not a merge gate. The workflow runs *after*
merge; branch protection required-check contexts only apply to PR-time events.
A red workflow run is a durable, searchable signal that a safety-gate-scope
merge lacked coordinator-ack. It complements the pre-PR hook which only
intercepts local `gh pr create`.

Per `.claude/rules/guards.md` Rule G1 (fail-closed defaults), every degenerate
input path exits non-zero with a clear message:

* missing/unresolvable base ref → exit 1
* `git diff` subprocess failure → exit 1 with stderr
* `gh api` unreachable / non-zero → exit 1
* malformed JSON response → exit 1
* missing allowlist file → exit 1
* empty allowlist after comment/blank stripping → exit 1

Per Rule G2 (content-derived sets), the safety-gate check uses the **path
regex** from `pre-pr-check.sh` — matching by path shape, not by a hardcoded
file-name list. Renames within a matching path pattern remain matched.

Usage:
    python scripts/check_post_merge_coordinator_ack.py \\
        --repo s5unanow/aeon-trespass-expert-1 \\
        --base <sha> --head <sha>

Both `--base` and `--head` default to `github.event.before` and `$GITHUB_SHA`
respectively (read from env vars when the `--base`/`--head` args are omitted),
so the workflow invocation is bare.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Safety-gate scope regex — MUST match the one in
# .claude/hooks/pre-pr-check.sh line 224 verbatim (modulo ERE/Python
# engine differences: here we use Python re, which understands the same
# character-class and anchor syntax). Any change here must be mirrored there.
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
        msg = (
            f"BLOCKED: git {' '.join(args)} failed (exit {result.returncode}).\n"
            f"  stderr: {result.stderr.strip()}\n"
            f"Per .claude/rules/guards.md Rule G1, git failures fail closed."
        )
        raise RuntimeError(msg)
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


def safety_gate_hits(paths: list[str]) -> list[str]:
    """Filter paths to the safety-gate subset."""
    return [p for p in paths if SAFETY_GATE_REGEX.match(p)]


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


def fetch_pull_numbers_for_commit(repo: str, sha: str) -> list[int]:
    """Find PR numbers whose merge commit equals sha. Empty list if none (not fatal)."""
    # Using /commits/<sha>/pulls which returns associated PRs.
    try:
        raw = _gh_api(f"repos/{repo}/commits/{sha}/pulls")
    except RuntimeError:
        # Treat as "no PRs found" — this endpoint is best-effort.
        return []
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
    """Return the newest success coordinator-ack from an allowlisted signer, or None.

    Follows the same latest-status-wins logic as `pre-pr-check.sh` (S5U-673):
    sort coordinator-ack statuses by created_at, take the most recent, and
    require it to be state=success AND creator in allowlist.
    """
    ack = [s for s in statuses if s.context == "coordinator-ack"]
    if not ack:
        return None
    ack_sorted = sorted(ack, key=lambda s: s.created_at)
    latest = ack_sorted[-1]
    if latest.state != "success":
        return None
    if latest.creator_login not in allowlist:
        return None
    return latest


def audit(
    *,
    repo: str,
    base: str,
    head: str,
    root: Path,
) -> int:
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

    # Determine the commit SHAs to check for coordinator-ack.
    # Strategy: start with the merge commit and every commit in the push range,
    # then augment with PR HEAD SHAs via gh api commits/<sha>/pulls.
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
    print(
        "BLOCKED: no valid coordinator-ack commit status found for the "
        "safety-gate-scope change in this push.\n"
        f"  Checked commits: {', '.join(sorted(s[:7] for s in commits_to_check))}\n"
        f"  Associated PRs:  {', '.join(str(n) for n in sorted(pr_numbers)) or '<none>'}\n"
        "\n"
        "Per CLAUDE.md step 6 and the S5U-693 post-merge audit rule, any\n"
        "safety-gate-scope merge must have a 'coordinator-ack' commit status\n"
        "(state=success) from an allowlisted signer on the PR HEAD SHA at\n"
        "merge time. This workflow is the post-merge audit trail that\n"
        "complements the pre-PR hook (which only intercepts local\n"
        "`gh pr create`)."
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
        return audit(
            repo=args.repo,
            base=args.base,
            head=args.head,
            root=args.repo_root,
        )
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

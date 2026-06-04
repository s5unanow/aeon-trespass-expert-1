"""Best-effort network signals for ``scripts/analytics_snapshot.py``.

Collects git stale-branch and ``gh`` CI-status signals. These are *optional*:
any subprocess failure (git/gh missing, offline, auth error, timeout) marks
only that field unavailable and never aborts the snapshot, so the aggregator
runs cleanly with no network and in CI.

Pure read-only — only read-only git/gh subcommands are invoked; nothing
mutates the repo, registry, or any artifact.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger("atr.analytics_snapshot")


class NetworkSignals(BaseModel):
    git_available: bool = False
    git_error: str | None = None
    local_branches: int = 0
    current_branch: str | None = None
    gh_available: bool = False
    gh_error: str | None = None
    latest_main_ci_conclusion: str | None = None


def _run(cmd: list[str], *, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def read_network_signals(repo_root: Path) -> NetworkSignals:
    """Collect best-effort git/gh signals. Any failure marks only that field.

    A subprocess failure (git/gh missing, offline, auth error, timeout) is
    captured into the corresponding ``*_error`` field; the snapshot is never
    aborted on account of network signals.
    """
    signals = NetworkSignals()
    _collect_git_signals(signals, repo_root)
    _collect_gh_signals(signals, repo_root)
    return signals


def _collect_git_signals(signals: NetworkSignals, repo_root: Path) -> None:
    try:
        branches = _run(["git", "-C", str(repo_root), "branch", "--list"])
        current = _run(["git", "-C", str(repo_root), "branch", "--show-current"])
    except (OSError, subprocess.SubprocessError) as exc:
        signals.git_error = f"git subprocess failed: {exc}"
        logger.warning("network/git unavailable: %s", exc)
        return
    if branches.returncode != 0:
        signals.git_error = f"git branch failed: {branches.stderr.strip()}"
        return
    signals.git_available = True
    signals.local_branches = len([ln for ln in branches.stdout.splitlines() if ln.strip()])
    signals.current_branch = current.stdout.strip() or None


def _collect_gh_signals(signals: NetworkSignals, repo_root: Path) -> None:
    try:
        proc = _run(
            [
                "gh",
                "run",
                "list",
                "--branch",
                "main",
                "--limit",
                "1",
                "--json",
                "conclusion",
            ]
        )
    except (OSError, subprocess.SubprocessError) as exc:
        signals.gh_error = f"gh subprocess failed: {exc}"
        logger.warning("network/gh unavailable: %s", exc)
        return
    if proc.returncode != 0:
        signals.gh_error = f"gh run list failed: {proc.stderr.strip() or 'non-zero exit'}"
        return
    try:
        runs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        signals.gh_error = f"gh output parse error: {exc}"
        return
    signals.gh_available = True
    if isinstance(runs, list) and runs and isinstance(runs[0], dict):
        concl = runs[0].get("conclusion")
        signals.latest_main_ci_conclusion = str(concl) if concl else None

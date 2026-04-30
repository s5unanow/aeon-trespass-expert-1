"""Shared helpers for the S5U-656 E2E test split of test_check_threshold_changes.

Used by:
- test_check_threshold_changes_e2e_happy.py
- test_check_threshold_changes_e2e_bypass.py

The leading underscore keeps pytest from collecting this module as a test file
(matches the repo convention used by scripts/_linear_client.py etc.).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_threshold_changes.py"

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")


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

#!/usr/bin/env python3
"""Audit live GitHub branch protection against repo workflow policy (S5U-709).

Usage:
    python scripts/check_branch_protection.py [--repo OWNER/REPO] [--branch main]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
MISSING = object()


@dataclass(frozen=True)
class LiveProtection:
    strict: bool
    enforce_admins: bool
    contexts: frozenset[str]


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow file and fail closed on malformed content."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised by unit tests
        raise RuntimeError(f"Failed to parse workflow YAML at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Workflow {path} did not parse to a mapping")
    return data


def parse_repo_slug(remote_url: str) -> str:
    """Extract OWNER/REPO from a GitHub remote URL."""
    patterns = (
        r"^git@github\.com:(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, remote_url.strip())
        if match:
            return match.group("slug")
    raise RuntimeError(f"Unsupported GitHub remote URL: {remote_url!r}")


def detect_repo_slug(repo_root: Path) -> str:
    """Read the local git remote and derive OWNER/REPO."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment failure
        raise RuntimeError("git not found; cannot detect repository slug") from exc
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to resolve git remote 'origin': "
            f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
    return parse_repo_slug(result.stdout)


def _workflow_on_block(workflow: dict[str, Any]) -> Any:
    """Return the `on:` block, handling YAML 1.1 bool coercion of `on` -> True."""
    if "on" in workflow:
        return workflow["on"]
    bool_key_value = workflow.get(cast(Any, True), MISSING)
    if bool_key_value is not MISSING:  # PyYAML treats bare `on:` as boolean True.
        return bool_key_value
    raise RuntimeError("Workflow is missing an 'on' block")


def _normalise_workflow_paths(repo_root: Path) -> list[Path]:
    """List workflow files under .github/workflows/ in stable order."""
    workflows_dir = repo_root / ".github" / "workflows"
    files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    if not files:
        raise RuntimeError(f"No workflow files found under {workflows_dir}")
    return files


def _pull_request_events(workflow: dict[str, Any], *, branch: str) -> set[str]:
    """Return the PR-style events the workflow runs for on the branch."""
    on_block = _workflow_on_block(workflow)
    if isinstance(on_block, str):
        return {on_block} if on_block in {"pull_request", "pull_request_target"} else set()
    if isinstance(on_block, list):
        return {
            event
            for event in on_block
            if isinstance(event, str) and event in {"pull_request", "pull_request_target"}
        }
    if not isinstance(on_block, dict):
        raise RuntimeError("Workflow 'on' block must be a scalar, list, or mapping")
    events: set[str] = set()
    for event_name in ("pull_request", "pull_request_target"):
        if event_name not in on_block:
            continue
        event_block = on_block[event_name]
        if event_block in (None, {}):
            events.add(event_name)
            continue
        if not isinstance(event_block, dict):
            raise RuntimeError(f"{event_name} trigger must be null or a mapping")
        if _event_matches_branch(event_block, branch):
            events.add(event_name)
    return events


def _branch_matches_pattern(branch: str, pattern: str) -> bool:
    """Match a GitHub branch glob using path-aware semantics."""
    return PurePosixPath(branch).match(pattern)


def _event_matches_branch(event_block: dict[str, Any], branch: str) -> bool:
    """Evaluate branches/branches-ignore filters for a PR-style event."""
    branches = event_block.get("branches")
    branches_ignore = event_block.get("branches-ignore")
    if branches is not None and branches_ignore is not None:
        raise RuntimeError("Workflow trigger cannot define both branches and branches-ignore")
    if branches is not None:
        branch_patterns = [branches] if isinstance(branches, str) else branches
        if not isinstance(branch_patterns, list) or not all(
            isinstance(item, str) for item in branch_patterns
        ):
            raise RuntimeError("Workflow branches filter must be a string or list of strings")
        return any(_branch_matches_pattern(branch, pattern) for pattern in branch_patterns)
    if branches_ignore is not None:
        ignore_patterns = [branches_ignore] if isinstance(branches_ignore, str) else branches_ignore
        if not isinstance(ignore_patterns, list) or not all(
            isinstance(item, str) for item in ignore_patterns
        ):
            raise RuntimeError(
                "Workflow branches-ignore filter must be a string or list of strings"
            )
        return not any(_branch_matches_pattern(branch, pattern) for pattern in ignore_patterns)
    return True


def _job_display_name(job_id: str, job_data: Any) -> str:
    """Return the emitted check-run display name for a workflow job."""
    if not isinstance(job_data, dict):
        raise RuntimeError(f"Job {job_id!r} did not parse to a mapping")
    name = job_data.get("name")
    if name is None:
        return job_id
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(f"Job {job_id!r} has a non-string or empty name")
    return name.strip()


def _job_runs_for_pr_events(job_data: dict[str, Any], pr_events: set[str]) -> bool:
    """Skip jobs whose simple event-name guard excludes every PR event.

    GitHub `if:` expressions are richer than we want to statically interpret
    here. We only special-case the simple `github.event_name ==/!= 'event'`
    guards that would otherwise overcount obviously non-emitted PR jobs.
    More complex expressions stay in-scope once the surrounding workflow
    itself is PR-triggered.
    """
    condition = job_data.get("if")
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    if not isinstance(condition, str) or not condition.strip():
        raise RuntimeError("Workflow job 'if' must be a non-empty string or bool")
    normalized = condition.strip()
    match = re.fullmatch(
        r"\${{\s*github\.event_name\s*([!=]=)\s*['\"]([^'\"]+)['\"]\s*}}"
        r"|github\.event_name\s*([!=]=)\s*['\"]([^'\"]+)['\"]",
        normalized,
    )
    if match is None:
        return True
    operator = match.group(1) or match.group(3)
    event_name = match.group(2) or match.group(4)
    if operator is None or event_name is None:
        raise RuntimeError("Failed to parse simple github.event_name guard")
    if operator == "==":
        return event_name in pr_events
    return any(candidate != event_name for candidate in pr_events)


def _expand_reusable_job_contexts(
    repo_root: Path,
    caller_job_id: str,
    job_data: dict[str, Any],
) -> set[str]:
    """Expand a local reusable workflow call into emitted check contexts."""
    uses = job_data.get("uses")
    if uses is None:
        return {_job_display_name(caller_job_id, job_data)}
    if not isinstance(uses, str):
        raise RuntimeError(f"Job {caller_job_id!r} has non-string 'uses'")
    if not uses.startswith("./.github/workflows/"):
        return {_job_display_name(caller_job_id, job_data)}
    called_path = repo_root / uses[2:]
    if not called_path.exists():
        raise RuntimeError(f"Reusable workflow {uses!r} referenced by {caller_job_id!r} not found")
    called_workflow = load_workflow(called_path)
    on_block = _workflow_on_block(called_workflow)
    is_workflow_call = (
        on_block == "workflow_call"
        or (isinstance(on_block, list) and "workflow_call" in on_block)
        or (isinstance(on_block, dict) and "workflow_call" in on_block)
    )
    if not is_workflow_call:
        raise RuntimeError(f"Reusable workflow {called_path} is missing workflow_call trigger")
    called_jobs = called_workflow.get("jobs")
    if not isinstance(called_jobs, dict) or not called_jobs:
        raise RuntimeError(f"Reusable workflow {called_path} has no jobs")
    return {
        f"{caller_job_id} / {_job_display_name(child_job_id, child_job)}"
        for child_job_id, child_job in called_jobs.items()
    }


def collect_expected_contexts(repo_root: Path, *, branch: str = "main") -> frozenset[str]:
    """Derive the blocking PR check contexts from repo workflow files."""
    contexts: set[str] = set()
    for workflow_path in _normalise_workflow_paths(repo_root):
        workflow = load_workflow(workflow_path)
        pr_events = _pull_request_events(workflow, branch=branch)
        if not pr_events:
            continue
        jobs = workflow.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            raise RuntimeError(f"Workflow {workflow_path} has no jobs")
        for job_id, job_data_any in jobs.items():
            if not isinstance(job_data_any, dict):
                raise RuntimeError(f"Workflow job {workflow_path}:{job_id} is not a mapping")
            if not _job_runs_for_pr_events(job_data_any, pr_events):
                continue
            job_contexts = _expand_reusable_job_contexts(repo_root, job_id, job_data_any)
            contexts.update(job_contexts)
    if not contexts:
        raise RuntimeError(f"No pull_request check contexts derived for branch {branch!r}")
    return frozenset(sorted(contexts))


def extract_live_protection(payload: dict[str, Any]) -> LiveProtection:
    """Validate the GitHub API payload and extract the fields we enforce."""
    required = payload.get("required_status_checks")
    if not isinstance(required, dict):
        raise RuntimeError("Live branch protection payload missing 'required_status_checks'")
    strict = required.get("strict")
    contexts = required.get("contexts")
    if not isinstance(strict, bool):
        raise RuntimeError(
            "Live branch protection payload missing boolean 'required_status_checks.strict'"
        )
    if not isinstance(contexts, list) or not all(isinstance(item, str) for item in contexts):
        raise RuntimeError(
            "Live branch protection payload missing string-list 'required_status_checks.contexts'"
        )
    enforce_admins = payload.get("enforce_admins")
    if not isinstance(enforce_admins, dict):
        raise RuntimeError("Live branch protection payload missing 'enforce_admins'")
    enabled = enforce_admins.get("enabled")
    if not isinstance(enabled, bool):
        raise RuntimeError(
            "Live branch protection payload missing boolean 'enforce_admins.enabled'"
        )
    return LiveProtection(
        strict=strict,
        enforce_admins=enabled,
        contexts=frozenset(contexts),
    )


def fetch_live_branch_protection(repo_slug: str, branch: str) -> LiveProtection:
    """Fetch live branch protection via `gh api` and validate the payload."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo_slug}/branches/{branch}/protection"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment failure
        raise RuntimeError("gh CLI not found; cannot audit live branch protection") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"gh api failed while reading branch protection: {stderr}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh api returned invalid JSON for branch protection") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("gh api branch protection response was not a JSON object")
    return extract_live_protection(payload)


def audit(repo_root: Path, live: LiveProtection, *, branch: str = "main") -> list[str]:
    """Compare live branch protection to the repo-derived policy."""
    expected_contexts = collect_expected_contexts(repo_root, branch=branch)
    findings: list[str] = []
    if not live.strict:
        findings.append("required_status_checks.strict is false; branch freshness is not enforced")
    if not live.enforce_admins:
        findings.append("enforce_admins.enabled is false; admins can bypass required checks")
    missing = sorted(expected_contexts - live.contexts)
    extra = sorted(live.contexts - expected_contexts)
    if missing:
        findings.append(f"missing required context(s): {', '.join(missing)}")
    if extra:
        findings.append(f"unexpected required context(s): {', '.join(extra)}")
    return findings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        help="GitHub repo slug (OWNER/REPO). Defaults to origin remote.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Protected branch to audit (default: main).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    repo_slug = args.repo or detect_repo_slug(REPO_ROOT)
    live = fetch_live_branch_protection(repo_slug, args.branch)
    findings = audit(REPO_ROOT, live, branch=args.branch)
    expected = sorted(collect_expected_contexts(REPO_ROOT, branch=args.branch))
    if findings:
        print(
            "FAIL: live branch protection for "
            f"{repo_slug}@{args.branch} does not match repo policy",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("  - expected required contexts:", file=sys.stderr)
        for context in expected:
            print(f"    * {context}", file=sys.stderr)
        return 1
    print(f"OK: live branch protection for {repo_slug}@{args.branch} matches repo policy")
    print(f"  strict={live.strict} enforce_admins={live.enforce_admins}")
    for context in expected:
        print(f"  - {context}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

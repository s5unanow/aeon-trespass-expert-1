#!/usr/bin/env python3
"""Validate every ``KNOWN_VIOLATORS`` Linear citation is an open tracker (S5U-669).

Meta-mitigation for the S5U-663 → S5U-669 drift class: a grandfather entry
that cites a ``Done`` or ``Canceled`` Linear issue is enforcement-wise
equivalent to no citation — a reviewer asked "what ticket covers this
file's split?" is handed a closed issue with no mandate.

This script imports ``scripts.check_file_length.KNOWN_VIOLATORS``,
deduplicates the value set, fetches each Linear issue via the shared
``_linear_client``, and fails if any resolves to ``state_type in
{"completed", "canceled"}`` (Linear's stable state enum — see
https://developers.linear.app/docs/graphql/working-with-the-graphql-api).

Runs in CI only (not pre-commit) because it hits the Linear API. Advisory
on first iteration — NOT wired to ``required_status_checks.contexts``.
Fails CLOSED on missing secret, malformed ID, API error, or deduplicated
empty set (per ``.claude/rules/guards.md`` Rule G1).

Usage (CI):
    LINEAR_API_KEY=... python scripts/check_file_length_violators_live.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Allow `python scripts/check_file_length_violators_live.py` invocation to
# resolve ``_linear_client`` (sibling module) without PYTHONPATH tweaks.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _linear_client import LinearAPIError, LinearIssue, fetch_linear_issue

ISSUE_ID_RE = re.compile(r"^S5U-(\d+)$")

# Linear state-type enum values that indicate the issue is closed / not an
# open tracker. Derived from Linear's WorkflowState.type documentation
# (https://developers.linear.app/docs/graphql/working-with-the-graphql-api).
# Other enum values ("triage", "backlog", "unstarted", "started") are open
# trackers; "unknown" is tolerated as schema-evolution-safe (a new enum
# value added by Linear should not retroactively break this gate).
STALE_STATE_TYPES = frozenset({"completed", "canceled"})

FetchIssue = Callable[[str, str], LinearIssue]


@dataclass(frozen=True)
class Violation:
    """One stale or malformed KNOWN_VIOLATORS entry."""

    issue_id: str
    reason: str
    affected_paths: list[str]


def _load_known_violators(script_path: Path) -> dict[str, str]:
    """Import ``check_file_length.KNOWN_VIOLATORS`` from ``script_path``.

    Uses a fresh import (not reliant on an installed package) so the script
    works in any CI working directory. Fail-closed on import errors.
    """
    spec = importlib.util.spec_from_file_location("_cfl_for_live_check", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {script_path} — spec_from_file_location returned None.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    violators = getattr(module, "KNOWN_VIOLATORS", None)
    if not isinstance(violators, dict):
        raise RuntimeError(
            f"{script_path} does not expose a dict attribute named KNOWN_VIOLATORS "
            f"(got {type(violators).__name__}). Has the attribute been renamed?"
        )
    return violators


def _group_paths_by_issue(violators: dict[str, str]) -> dict[str, list[str]]:
    """Return ``{issue_id: [path, ...]}`` so we can dedupe Linear API calls."""
    grouped: dict[str, list[str]] = {}
    for path, issue_id in violators.items():
        grouped.setdefault(issue_id, []).append(path)
    return grouped


def _parse_issue_number(issue_id: str) -> str | None:
    """Return the numeric portion of ``S5U-<N>`` or None if malformed."""
    match = ISSUE_ID_RE.match(issue_id)
    if match is None:
        return None
    return match.group(1)


def scan(
    violators: dict[str, str],
    api_key: str,
    fetch_issue: FetchIssue = fetch_linear_issue,
) -> list[Violation]:
    """Run the live check and return the list of stale / malformed citations.

    Empty list means all citations resolve to open Linear issues.
    """
    if not api_key:
        # Caller converts this to exit 1 with a CLI-facing message. Signalled
        # via ``Violation(issue_id="", ...)`` for test symmetry.
        return [
            Violation(
                issue_id="",
                reason=(
                    "LINEAR_API_KEY not set — fail-CLOSED. Configure the repo "
                    "secret before this gate can verify citations."
                ),
                affected_paths=sorted(violators.keys()),
            )
        ]

    grouped = _group_paths_by_issue(violators)
    violations: list[Violation] = []
    for issue_id, paths in sorted(grouped.items()):
        number = _parse_issue_number(issue_id)
        if number is None:
            violations.append(
                Violation(
                    issue_id=issue_id,
                    reason=(f"Unparseable Linear ID {issue_id!r} — expected format S5U-<number>."),
                    affected_paths=sorted(paths),
                )
            )
            continue

        try:
            issue = fetch_issue(number, api_key)
        except LinearAPIError as exc:
            violations.append(
                Violation(
                    issue_id=issue_id,
                    reason=f"Linear API error (fail-CLOSED): {exc}",
                    affected_paths=sorted(paths),
                )
            )
            continue

        if issue.state_type in STALE_STATE_TYPES:
            violations.append(
                Violation(
                    issue_id=issue.identifier,
                    reason=(
                        f"Linear issue {issue.identifier} is "
                        f"{issue.state_name!r} (state_type="
                        f"{issue.state_type!r}) — KNOWN_VIOLATORS cannot "
                        "cite a closed issue as an open tracker. Open a "
                        "new follow-up and re-key these entries."
                    ),
                    affected_paths=sorted(paths),
                )
            )

    return violations


def format_report(violations: list[Violation]) -> str:
    """Render violations into a human-readable multi-line report."""
    lines: list[str] = []
    for v in violations:
        header = f"STALE CITATION {v.issue_id!r}:" if v.issue_id else "CONFIG ERROR:"
        lines.append(header)
        lines.append(f"  reason: {v.reason}")
        lines.append("  affected paths:")
        for path in v.affected_paths:
            lines.append(f"    - {path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate every scripts/check_file_length.py:KNOWN_VIOLATORS "
            "value resolves to a non-Done / non-Canceled Linear issue "
            "(S5U-669)."
        ),
    )
    parser.add_argument(
        "--check-file-length-path",
        type=Path,
        default=Path(__file__).resolve().parent / "check_file_length.py",
        help="Path to check_file_length.py (default: sibling in scripts/).",
    )
    args = parser.parse_args(argv)

    try:
        violators = _load_known_violators(args.check_file_length_path)
    except Exception as exc:
        print(
            f"::error::check_file_length_violators_live: cannot load "
            f"KNOWN_VIOLATORS from {args.check_file_length_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    if not violators:
        # Empty map is benign: nothing to check.
        print("check_file_length_violators_live: KNOWN_VIOLATORS is empty — nothing to verify.")
        return 0

    api_key = os.environ.get("LINEAR_API_KEY", "")
    violations = scan(violators, api_key)
    if violations:
        print(
            "::error::check_file_length_violators_live: stale or malformed "
            "Linear citations in KNOWN_VIOLATORS:",
            file=sys.stderr,
        )
        print(format_report(violations), file=sys.stderr)
        return 1

    unique_ids = sorted(set(violators.values()))
    print(
        "check_file_length_violators_live: OK — "
        f"{len(unique_ids)} unique Linear issue(s) all resolve to open trackers: "
        f"{', '.join(unique_ids)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

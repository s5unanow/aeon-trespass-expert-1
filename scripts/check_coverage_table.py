#!/usr/bin/env python3
"""CI-level Coverage-table scan (S5U-620).

Closes the bypass surfaced by S5U-620: after `gh pr create`, the worker can
run `gh pr edit --body <stripped>` to remove the `## Coverage` section from
the PR body. This script re-validates the PR body at every
`pull_request: [opened, synchronize, edited, reopened]` event.

Contract mirrors `.claude/prompts/linear-conventions.md` § "Coverage table
format" and `.claude/prompts/review.md` check #19. Fail-CLOSED on every
unresolvable state (bad branch name, missing secret, Linear API error,
deferred-to-Canceled/non-existent issue).

Usage (CI):
    python scripts/check_coverage_table.py --branch "$GITHUB_HEAD_REF" \\
        --pr-body-file pr_body.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Allow `python scripts/check_coverage_table.py` invocation to resolve
# `_linear_client` (sibling module) without requiring PYTHONPATH tweaks.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _linear_client import LinearAPIError, LinearIssue, fetch_linear_issue

COVERAGE_THRESHOLD = 3

BRANCH_ISSUE_RE = re.compile(r"(?i)s5u-(\d+)")

# Any heading level whose text contains the word "coverage" (case-
# insensitive), optionally followed by arbitrary words. Tolerates
# `## Coverage`, `# Coverage`, `### Coverage Table`, etc.
_COVERAGE_HEADING_RE = re.compile(r"^\s*#{1,6}\s*coverage\b.*$", re.IGNORECASE | re.MULTILINE)

# Strip triple-backtick/tilde fenced blocks before counting bullets.
_FENCE_RE = re.compile(r"^(```|~~~).*?^(```|~~~)\s*$", re.DOTALL | re.MULTILINE)

# List marker: dash, star, plus, or numbered. Require one character of body
# to avoid counting blank bullet lines.
_LIST_MARKER_RE = re.compile(r"^(?P<indent>[\t ]*)(?:[-*+]|\d+\.)\s+\S")

_SECTION_START_FIX_RE = re.compile(r"(?i)^\**\s*fix\b")
_SECTION_START_SUCCESS_RE = re.compile(r"(?i)^\**\s*success\s*criteria\b")

_DEFERRED_ISSUE_RE = re.compile(r"(?i)\bs5u-(\d+)\b")


@dataclass(frozen=True)
class BulletCountResult:
    """Result of counting bullets in a Linear description."""

    total: int
    top_level: int
    nested: int


# ----------------------------------------------------------------------
# Branch-name parsing
# ----------------------------------------------------------------------


def extract_issue_id_from_branch(branch: str) -> str | None:
    """Return the numeric Linear issue ID or None if the branch has no ID.

    First match wins, mirroring `.claude/hooks/pre-pr-check.sh:15`.
    """
    match = BRANCH_ISSUE_RE.search(branch)
    if match is None:
        return None
    return match.group(1)


# ----------------------------------------------------------------------
# Linear description parsing
# ----------------------------------------------------------------------


def strip_fenced_code_blocks(text: str) -> str:
    """Remove triple-backtick / triple-tilde fenced code blocks."""
    return _FENCE_RE.sub("", text)


def iter_fix_and_success_sections(description: str) -> list[str]:
    """Extract bodies of 'Fix' and 'Success criteria' sections.

    Also recognizes bold pseudo-headings (`**Fix sketch**`) which Linear
    users commonly write. The body of each section ends at the next
    heading (any level) or EOF.
    """
    headings: list[tuple[int, str, str]] = []
    for match in re.finditer(r"(?m)^(\s*)(#{1,6})\s*(.+?)\s*$", description):
        headings.append((match.start(), match.group(2), match.group(3)))
    for match in re.finditer(r"(?m)^\s*(\*\*|__)\s*(.+?)\s*\1\s*$", description):
        headings.append((match.start(), "##", match.group(2)))
    headings.sort(key=lambda h: h[0])

    results: list[str] = []
    for i, (start, _level, title) in enumerate(headings):
        if not (_SECTION_START_FIX_RE.match(title) or _SECTION_START_SUCCESS_RE.match(title)):
            continue
        body_start = description.find("\n", start)
        if body_start == -1:
            continue
        body_start += 1
        body_end = headings[i + 1][0] if i + 1 < len(headings) else len(description)
        results.append(description[body_start:body_end])
    return results


def count_bullets(description: str) -> BulletCountResult:
    """Count every list marker at every indent level in Fix + Success.

    Nested sub-bullets count as separate bullets (S5U-622 rule).
    Fenced code blocks are stripped before counting.
    """
    clean = strip_fenced_code_blocks(description)
    top_level = 0
    nested = 0
    for body in iter_fix_and_success_sections(clean):
        for line in body.splitlines():
            match = _LIST_MARKER_RE.match(line)
            if match is None:
                continue
            # Normalize tabs to 4 spaces for indent measurement.
            visual_indent = len(match.group("indent").replace("\t", "    "))
            if visual_indent == 0:
                top_level += 1
            else:
                nested += 1
    return BulletCountResult(total=top_level + nested, top_level=top_level, nested=nested)


# ----------------------------------------------------------------------
# PR body parsing
# ----------------------------------------------------------------------


def find_coverage_section(pr_body: str) -> str | None:
    """Return the text of the ## Coverage section, or None if absent.

    HTML comments wrapping the section are treated as absent (fail-CLOSED).
    """
    stripped = re.sub(r"<!--.*?-->", "", pr_body, flags=re.DOTALL)
    match = _COVERAGE_HEADING_RE.search(stripped)
    if match is None:
        return None
    body_start = match.end()
    next_heading = re.search(r"(?m)^\s*#{1,6}\s", stripped[body_start:])
    body_end = body_start + next_heading.start() if next_heading else len(stripped)
    return stripped[body_start:body_end]


def count_table_data_rows(section_text: str) -> int:
    """Count data rows in the first Markdown table inside `section_text`.

    A Markdown table has: header, separator (`|----|`), then data rows.
    Returns 0 if no separator is present (malformed table).
    """
    data_rows = 0
    passed_separator = False
    for raw in section_text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            if passed_separator and not line:
                continue
            if passed_separator:
                break
            continue
        if re.fullmatch(r"\|[\s\-:|]+\|", line):
            passed_separator = True
            continue
        if passed_separator:
            data_rows += 1
    return data_rows


def extract_deferred_issue_ids(section_text: str) -> list[str]:
    """Return all 'deferred to S5U-<N>' IDs from the coverage section."""
    ids: list[str] = []
    for raw in section_text.splitlines():
        if "defer" not in raw.lower():
            continue
        ids.extend(match.group(1) for match in _DEFERRED_ISSUE_RE.finditer(raw))
    return ids


# ----------------------------------------------------------------------
# Main validation
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Final verdict with diagnostic."""

    ok: bool
    message: str


FetchIssue = Callable[[str, str], LinearIssue]


def _validate_deferred_rows(
    deferred_ids: list[str],
    api_key: str,
    fetch_issue: FetchIssue,
) -> ValidationResult | None:
    """Verify every deferred Linear ID exists and is not Canceled."""
    for deferred in deferred_ids:
        try:
            follow_up = fetch_issue(deferred, api_key)
        except LinearAPIError as exc:
            return ValidationResult(
                ok=False,
                message=(
                    f"Deferred Linear issue S5U-{deferred} could not be "
                    f"verified (fail-CLOSED): {exc}"
                ),
            )
        if follow_up.state_name == "Canceled":
            return ValidationResult(
                ok=False,
                message=(
                    f"Deferred follow-up {follow_up.identifier} is Canceled — "
                    "cannot treat the row as legitimately deferred."
                ),
            )
    return None


def validate(
    *,
    branch: str,
    pr_body: str,
    api_key: str,
    fetch_issue: FetchIssue = fetch_linear_issue,
) -> ValidationResult:
    """Run the full validation. Pure-ish (inputs + injected fetcher)."""
    issue_num = extract_issue_id_from_branch(branch)
    if issue_num is None:
        return ValidationResult(
            ok=False,
            message=(
                f"Cannot extract Linear issue ID from branch name {branch!r}. "
                "Expected s5unanow/s5u-<NUMBER>-<description>."
            ),
        )
    if not api_key:
        return ValidationResult(
            ok=False,
            message=(
                "LINEAR_API_KEY not configured. Set the repo secret before "
                "this CI gate can run. See tmp/plan-s5u-620.md § "
                "'Secret-provisioning decision' for operator instructions."
            ),
        )

    try:
        issue = fetch_issue(issue_num, api_key)
    except LinearAPIError as exc:
        return ValidationResult(ok=False, message=f"Linear API error (fail-CLOSED): {exc}")

    bullets = count_bullets(issue.description)
    if bullets.total < COVERAGE_THRESHOLD:
        return ValidationResult(
            ok=True,
            message=(
                f"Issue {issue.identifier} has {bullets.total} bullet(s) — "
                f"below the {COVERAGE_THRESHOLD}-bullet threshold; Coverage "
                "table is optional."
            ),
        )

    coverage_section = find_coverage_section(pr_body)
    if coverage_section is None:
        return ValidationResult(
            ok=False,
            message=(
                f"Multi-bullet issue {issue.identifier} has {bullets.total} "
                f"bullets ({bullets.top_level} top-level + {bullets.nested} "
                "nested); PR body lacks a '## Coverage' section. Restore the "
                "Coverage table per .claude/prompts/linear-conventions.md § "
                "'Coverage table format'."
            ),
        )

    row_count = count_table_data_rows(coverage_section)
    if row_count < bullets.total:
        return ValidationResult(
            ok=False,
            message=(
                f"Coverage table has {row_count} data row(s) but issue "
                f"{issue.identifier} has {bullets.total} bullets "
                f"({bullets.top_level} top-level + {bullets.nested} nested). "
                "S5U-622 rule: every list marker at every indent level is "
                "one row — do not collapse nested sub-bullets under parent "
                "rows."
            ),
        )

    deferred_ids = extract_deferred_issue_ids(coverage_section)
    deferred_result = _validate_deferred_rows(deferred_ids, api_key, fetch_issue)
    if deferred_result is not None:
        return deferred_result

    return ValidationResult(
        ok=True,
        message=(
            f"Issue {issue.identifier}: {bullets.total} bullets matched by "
            f"{row_count} Coverage row(s); {len(deferred_ids)} deferral(s) "
            "verified."
        ),
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Validate PR body Coverage table against Linear bullets (S5U-620)."),
    )
    parser.add_argument("--branch", required=True, help="Git branch name.")
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        required=True,
        help="Path to a file containing the PR body markdown.",
    )
    args = parser.parse_args(argv)

    try:
        pr_body = args.pr_body_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::check_coverage_table: cannot read PR body file: {exc}")
        return 1

    api_key = os.environ.get("LINEAR_API_KEY", "")
    result = validate(branch=args.branch, pr_body=pr_body, api_key=api_key)
    if result.ok:
        print(f"check_coverage_table: OK — {result.message}")
        return 0
    print(f"::error::check_coverage_table: {result.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

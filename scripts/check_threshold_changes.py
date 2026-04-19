#!/usr/bin/env python3
"""CI guard: prevent silent loosening of extraction thresholds.

Blocks a PR when `configs/qa/thresholds.toml` is loosened without
justification. See docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md §8.3 and
`tmp/plan-s5u-591.md` for the full design rationale.

A change is considered LOOSENING when any of the following is true for
an entry keyed by `name`:

  * post-change `min` is numerically less than pre-change `min`
  * post-change `blocking` is False and pre-change `blocking` was True
  * the entry is deleted (no matching `name` on the head side)

A change is considered TIGHTENING (or neutral) when:

  * `min` is raised or unchanged
  * `blocking` is added or left True
  * net-new entries are added
  * only `description` / ordering / whitespace / comments change

Justification mechanisms — either is sufficient:

  1. Commit-message sentinel: a line matching `LOOSEN-THRESHOLD: <reason>`
     (case-insensitive) with non-empty reason text, present in at least one
     commit in `base..head` that touches the thresholds file. This is the
     primary mechanism because it survives in git history.

  2. PR-body sentinel: a `## Threshold loosening justification` heading
     (exactly that text, case-insensitive, level H1-H6) followed by a
     non-blank body line, in the file passed via `--pr-body-file`. CI
     passes the live PR body to this path.

Usage:

    uv run python scripts/check_threshold_changes.py \\
        --base origin/main --head HEAD [--pr-body-file pr_body.md]

Exit 0: no loosening, or loosening is justified.
Exit 1: loosening detected without justification.

Design note: this script uses `tomllib` directly rather than importing
`atr_pipeline.eval.thresholds.ThresholdConfig` to keep the CI step
dependency-free (no `uv sync` needed to invoke it, matching the
coverage-table scan pattern). Parsing mirrors the Pydantic model's
field names; if the schema drifts, update `_parse_thresholds`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

THRESHOLDS_PATH = "configs/qa/thresholds.toml"

# Commit-message sentinel. Require non-empty reason after the colon.
# Match anywhere on a line so "  LOOSEN-THRESHOLD: recalibrated" inside
# a multi-line body still counts.
_COMMIT_SENTINEL_RE = re.compile(
    r"(?im)^[\s>]*loosen[-_]threshold\s*:\s*(\S.*)$",
)

# PR-body heading: "## Threshold loosening justification" (H1-H6, any case).
_PR_HEADING_RE = re.compile(
    r"(?im)^\s*#{1,6}\s*threshold\s+loosening\s+justification\b.*$",
)


@dataclass(frozen=True)
class ThresholdEntry:
    """One [[metric_thresholds]] entry, keyed by name."""

    name: str
    min: float
    blocking: bool


# ---------------------------------------------------------------------------
# Git / IO helpers
# ---------------------------------------------------------------------------


def _git_show(ref: str, path: str) -> str | None:
    """Return file contents at `ref`, or None if the file doesn't exist there."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _get_commits_touching(base: str, head: str, path: str) -> list[str]:
    """Return full commit messages (subject+body) for commits in base..head touching path."""
    # %B = raw body (subject + body). %x00 separator because commit messages can
    # contain any other character including newlines.
    result = subprocess.run(
        ["git", "log", f"{base}..{head}", "--format=%B%x00", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [msg for msg in result.stdout.split("\x00") if msg.strip()]


# ---------------------------------------------------------------------------
# Threshold parsing
# ---------------------------------------------------------------------------


def _parse_thresholds(toml_text: str | None) -> dict[str, ThresholdEntry]:
    """Parse TOML text and return {name: ThresholdEntry}.

    Missing file returns empty dict. Malformed entries (missing name, missing
    min) are skipped — the pipeline's own Pydantic loader will reject those at
    runtime; here we don't want to block the CI gate on an unrelated schema
    error.
    """
    if toml_text is None:
        return {}
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        # A malformed head-side file is a hard block: we can't verify that
        # thresholds haven't been loosened if we can't parse them.
        raise SystemExit(f"ERROR: failed to parse thresholds TOML: {exc}") from exc

    entries: dict[str, ThresholdEntry] = {}
    for raw in data.get("metric_thresholds", []):
        name = raw.get("name")
        if not isinstance(name, str):
            continue
        min_val = raw.get("min")
        if not isinstance(min_val, (int, float)):
            continue
        blocking = bool(raw.get("blocking", True))
        entries[name] = ThresholdEntry(name=name, min=float(min_val), blocking=blocking)
    return entries


# ---------------------------------------------------------------------------
# Loosening detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LooseningFinding:
    """Describes one loosening event between base and head."""

    name: str
    kind: str  # "min_lowered" | "blocking_disabled" | "deleted"
    before: str
    after: str

    def render(self) -> str:
        return f"  - {self.name}: {self.kind} ({self.before} -> {self.after})"


def detect_loosening(
    base: dict[str, ThresholdEntry],
    head: dict[str, ThresholdEntry],
) -> list[LooseningFinding]:
    """Return all loosening findings. Empty list means no loosening."""
    findings: list[LooseningFinding] = []
    for name, base_entry in base.items():
        head_entry = head.get(name)
        if head_entry is None:
            findings.append(
                LooseningFinding(
                    name=name,
                    kind="deleted",
                    before=f"min={base_entry.min}, blocking={base_entry.blocking}",
                    after="(entry removed)",
                )
            )
            continue
        if head_entry.min < base_entry.min:
            findings.append(
                LooseningFinding(
                    name=name,
                    kind="min_lowered",
                    before=f"min={base_entry.min}",
                    after=f"min={head_entry.min}",
                )
            )
        if base_entry.blocking and not head_entry.blocking:
            findings.append(
                LooseningFinding(
                    name=name,
                    kind="blocking_disabled",
                    before="blocking=true",
                    after="blocking=false",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Justification detection
# ---------------------------------------------------------------------------


def has_commit_sentinel(commit_messages: list[str]) -> tuple[bool, str]:
    """Return (found, reason) for first non-empty LOOSEN-THRESHOLD sentinel."""
    for msg in commit_messages:
        match = _COMMIT_SENTINEL_RE.search(msg)
        if match is None:
            continue
        reason = match.group(1).strip()
        if reason:
            return True, reason
    return False, ""


def has_pr_body_sentinel(pr_body_path: Path | None) -> tuple[bool, str]:
    """Return (found, excerpt) if a non-empty justification section is present.

    We require the heading to be followed by at least one non-blank,
    non-heading line — a bare heading is not a justification.
    """
    if pr_body_path is None or not pr_body_path.exists():
        return False, ""
    text = pr_body_path.read_text(encoding="utf-8")
    match = _PR_HEADING_RE.search(text)
    if match is None:
        return False, ""
    # Walk lines after the heading, looking for non-empty, non-heading content.
    after = text[match.end() :]
    for line in after.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Next heading without any body content between — no justification.
            return False, ""
        return True, stripped[:120]
    return False, ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--base", required=True, help="Base ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head ref")
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        default=None,
        help="Optional path to a file containing the PR body (CI passes this).",
    )
    args = parser.parse_args()

    base_text = _git_show(args.base, THRESHOLDS_PATH)
    head_text = _git_show(args.head, THRESHOLDS_PATH)

    if base_text is None and head_text is None:
        print("No thresholds file at base or head. Guard passes.")
        return 0

    if base_text == head_text:
        print("Thresholds file unchanged. Guard passes.")
        return 0

    base_map = _parse_thresholds(base_text)
    head_map = _parse_thresholds(head_text)

    findings = detect_loosening(base_map, head_map)

    if not findings:
        print("Thresholds file changed, but no loosening detected. Guard passes.")
        return 0

    print(f"Detected {len(findings)} threshold loosening change(s):")
    for finding in findings:
        print(finding.render())

    commit_messages = _get_commits_touching(args.base, args.head, THRESHOLDS_PATH)
    commit_ok, commit_reason = has_commit_sentinel(commit_messages)
    if commit_ok:
        print(f"\nJustification found in commit message: {commit_reason}")
        print("Guard passes.")
        return 0

    body_ok, body_excerpt = has_pr_body_sentinel(args.pr_body_file)
    if body_ok:
        print(f"\nJustification found in PR body: {body_excerpt}")
        print("Guard passes.")
        return 0

    print(
        "\nBLOCK: threshold loosening detected without justification.\n"
        "To unblock, add ONE of:\n"
        "  * A line 'LOOSEN-THRESHOLD: <reason>' in a commit that touches\n"
        "    configs/qa/thresholds.toml (case-insensitive; reason must be\n"
        "    non-empty).\n"
        "  * A '## Threshold loosening justification' heading in the PR\n"
        "    body, followed by at least one non-blank line explaining the\n"
        "    change and linking any calibration data.\n"
        "See docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md §8.3."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

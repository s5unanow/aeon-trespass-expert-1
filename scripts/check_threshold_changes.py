#!/usr/bin/env python3
"""CI guard: prevent silent loosening of extraction thresholds.

S5U-643: per-finding justification. Each loosening in
`configs/qa/thresholds.toml` must be covered by EITHER a sentinel on the
responsible commit (`LOOSEN-THRESHOLD: <name>[, ...] <sep> <reason>`)
or a PR-body bullet (`- <name>: <reason>` under `## Threshold loosening
justification`). See docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md §8.3.

Usage:
    uv run python scripts/check_threshold_changes.py \\
        --base origin/main --head HEAD [--pr-body-file pr_body.md]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from _git_baseline import verify_ref_exists

THRESHOLDS_PATH = "configs/qa/thresholds.toml"

# S5U-643: per-finding commit-message sentinel.
# Matches e.g.:
#   LOOSEN-THRESHOLD: foo_pass_rate — dataset refresh
#   LOOSEN-THRESHOLD: foo, bar -- recalibrated
#   loosen-threshold: foo: see audit
# Rejects: no names, no separator, or empty reason.
_COMMIT_SENTINEL_RE = re.compile(
    r"(?im)^[\s>]*loosen[-_]threshold\s*:\s*"
    r"(?P<names>[^\n—:]+?)"
    r"\s*(?:—|--|-|:)\s*"
    r"(?P<reason>\S.*)$",
)

_PR_HEADING_RE = re.compile(
    r"(?im)^\s*#{1,6}\s*threshold\s+loosening\s+justification\b.*$",
)

# Per-finding bullet under the heading: `- <name>: <reason>`.
_PR_BULLET_RE = re.compile(
    r"(?im)^\s*[-*+]\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*:\s*"
    r"(?P<reason>\S.*)$",
)

_PR_ANY_HEADING_RE = re.compile(r"(?m)^\s*#{1,6}\s+")


@dataclass(frozen=True)
class ThresholdEntry:
    name: str
    min: float
    blocking: bool


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def _git_show(ref: str, path: str) -> str | None:
    """Return file contents at `ref`, or None if path is absent at that commit."""
    result = _run_git("show", f"{ref}:{path}")
    return None if result.returncode != 0 else result.stdout


def _get_commit_message(sha: str) -> str:
    """Return full commit message for `sha`. Fails closed on git error."""
    result = _run_git("log", "-1", "--format=%B", sha)
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git log -1 --format=%B {sha} failed: {result.stderr.strip()}")
    return result.stdout


def _get_commits_touching(base: str, head: str, path: str) -> list[str]:
    """Return SHAs (newest→oldest) in base..head that touch `path`. Fails closed."""
    result = _run_git("log", f"{base}..{head}", "--format=%H", "--", path)
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git log {base}..{head} -- {path} failed: {result.stderr.strip()}")
    return [sha for sha in result.stdout.splitlines() if sha.strip()]


def _commit_parent(sha: str) -> str | None:
    """First-parent SHA of `sha`, or None for root commit."""
    result = _run_git("rev-parse", f"{sha}^")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _parse_thresholds(toml_text: str | None) -> dict[str, ThresholdEntry]:
    """Parse TOML → {name: ThresholdEntry}. Missing file → empty dict."""
    if toml_text is None:
        return {}
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"ERROR: failed to parse thresholds TOML: {exc}") from exc

    entries: dict[str, ThresholdEntry] = {}
    for raw in data.get("metric_thresholds", []):
        name = raw.get("name")
        if not isinstance(name, str):
            continue
        min_val = raw.get("min")
        # Reject bool (subclass of int) so `min = true` doesn't parse as 1.0.
        if not isinstance(min_val, (int, float)) or isinstance(min_val, bool):
            continue
        # S5U-644: match runtime Pydantic bool boundary. Reject non-bool
        # including strings ("false" is Python-truthy) and ints.
        raw_blocking = raw.get("blocking", True)
        if not isinstance(raw_blocking, bool):
            raise SystemExit(
                f"ERROR: [metric_thresholds.{name}].blocking must be a TOML "
                f"boolean (true/false), got {type(raw_blocking).__name__} "
                f"{raw_blocking!r}. See apps/pipeline/src/atr_pipeline/eval/"
                "thresholds.py — the runtime model requires bool."
            )
        entries[name] = ThresholdEntry(name=name, min=float(min_val), blocking=raw_blocking)
    return entries


def _parse_thresholds_at(ref: str) -> dict[str, ThresholdEntry]:
    """Parse thresholds.toml at `ref`. Adds commit context on parse failure."""
    text = _git_show(ref, THRESHOLDS_PATH)
    try:
        return _parse_thresholds(text)
    except SystemExit as exc:
        raise SystemExit(f"ERROR: parsing {THRESHOLDS_PATH} at {ref} failed: {exc}") from exc


@dataclass(frozen=True)
class LooseningFinding:
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


# --- Responsible-commit resolution (S5U-643) ---


def _finding_applies_at_transition(
    finding: LooseningFinding,
    pre: dict[str, ThresholdEntry],
    post: dict[str, ThresholdEntry],
) -> bool:
    """True iff `finding`'s loosening manifests at this commit's pre→post boundary."""
    pre_entry = pre.get(finding.name)
    post_entry = post.get(finding.name)
    if finding.kind == "deleted":
        return pre_entry is not None and post_entry is None
    if finding.kind == "min_lowered":
        if pre_entry is None or post_entry is None:
            return False
        return post_entry.min < pre_entry.min
    if finding.kind == "blocking_disabled":
        if pre_entry is None or post_entry is None:
            return False
        return pre_entry.blocking and not post_entry.blocking
    return False


def find_responsible_commit(
    finding: LooseningFinding,
    base: str,
    head: str,
) -> str:
    """Identify the commit in base..head that introduced `finding`. Fails closed."""
    shas = _get_commits_touching(base, head, THRESHOLDS_PATH)
    if not shas:
        raise SystemExit(
            f"ERROR: no commit in {base}..{head} touches {THRESHOLDS_PATH}, "
            f"yet a loosening was detected for '{finding.name}'. This usually "
            "means --base is stale or points outside the PR's commit range. "
            "Cannot attribute the loosening to a responsible commit; failing "
            "closed."
        )
    for sha in shas:
        parent = _commit_parent(sha)
        pre = _parse_thresholds_at(parent) if parent else {}
        post = _parse_thresholds_at(sha)
        if _finding_applies_at_transition(finding, pre, post):
            return sha
    raise SystemExit(
        f"ERROR: could not identify the commit in {base}..{head} that "
        f"introduced loosening for '{finding.name}' ({finding.kind}: "
        f"{finding.before} -> {finding.after}). Likely cause: the change "
        "crosses multiple commits that partially offset, or --base is "
        "misconfigured. Squash into one commit and re-run."
    )


# --- Per-finding justification ---


def _normalize_names(raw_names: str) -> list[str]:
    """Split a names list into lowercased, stripped identifiers."""
    return [n.strip().lower() for n in raw_names.split(",") if n.strip()]


def commit_sentinel_covers(finding_name: str, commit_message: str) -> tuple[bool, str]:
    """True iff a `LOOSEN-THRESHOLD:` sentinel in `commit_message` names `finding_name`."""
    target = finding_name.lower()
    for match in _COMMIT_SENTINEL_RE.finditer(commit_message):
        reason = match.group("reason").strip()
        if not reason:
            continue
        if target in _normalize_names(match.group("names")):
            return True, reason
    return False, ""


def pr_body_covers(finding_name: str, pr_body_path: Path | None) -> tuple[bool, str]:
    """True iff PR body has a `- <finding_name>: <reason>` bullet under the heading."""
    if pr_body_path is None or not pr_body_path.exists():
        return False, ""
    try:
        text = pr_body_path.read_text(encoding="utf-8")
    except OSError:
        return False, ""
    heading = _PR_HEADING_RE.search(text)
    if heading is None:
        return False, ""
    after = text[heading.end() :]
    next_heading = _PR_ANY_HEADING_RE.search(after)
    section = after[: next_heading.start()] if next_heading else after
    target = finding_name.lower()
    for bullet in _PR_BULLET_RE.finditer(section):
        if bullet.group("name").strip().lower() == target:
            reason = bullet.group("reason").strip()
            if reason:
                return True, reason
    return False, ""


def _justify_findings(
    findings: list[LooseningFinding],
    base: str,
    head: str,
    pr_body_path: Path | None,
) -> list[tuple[LooseningFinding, str]]:
    """Return [(finding, miss_reason), ...] for findings lacking justification."""
    missing: list[tuple[LooseningFinding, str]] = []
    for finding in findings:
        responsible_sha = find_responsible_commit(finding, base, head)
        commit_msg = _get_commit_message(responsible_sha)
        ok, reason = commit_sentinel_covers(finding.name, commit_msg)
        if ok:
            print(
                f"  * {finding.name}: justified by commit {responsible_sha[:12]} "
                f'sentinel — "{reason[:80]}"'
            )
            continue
        ok, reason = pr_body_covers(finding.name, pr_body_path)
        if ok:
            print(f'  * {finding.name}: justified by PR body bullet — "{reason[:80]}"')
            continue
        missing.append(
            (
                finding,
                f"responsible commit {responsible_sha[:12]} has no "
                f"'LOOSEN-THRESHOLD: {finding.name} ...' sentinel, and PR body "
                f"has no '- {finding.name}: ...' bullet under '## Threshold "
                "loosening justification'",
            )
        )
    return missing


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

    # S5U-642: resolve both refs BEFORE attempting `git show`; shallow
    # checkouts otherwise present as "every threshold is net-new."
    verify_ref_exists(args.base)
    verify_ref_exists(args.head)

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

    print("\nChecking per-finding justification:")
    missing = _justify_findings(findings, args.base, args.head, args.pr_body_file)

    if not missing:
        print("\nAll loosenings justified. Guard passes.")
        return 0

    print("\nBLOCK: threshold loosening detected without per-finding justification.")
    for finding, why in missing:
        print(f"  - {finding.name} ({finding.kind}): {why}")
    print(
        "\nTo unblock, for EACH unjustified finding provide ONE of:\n"
        "  * 'LOOSEN-THRESHOLD: <name>[, ...] <sep> <reason>' in the commit\n"
        "    that introduced the loosening. <sep> is '—', '--', '-', or ':'.\n"
        "    Names must include the loosened threshold (case-insensitive).\n"
        "  * A '- <name>: <reason>' bullet under a '## Threshold loosening\n"
        "    justification' heading in the PR body.\n"
        "See docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md §8.3."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

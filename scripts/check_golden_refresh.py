#!/usr/bin/env python3
"""CI guard: prevent silent golden fixture overwrites.

Checks that any changes to expected/ golden files follow the governance rules:
1. Golden changes are in dedicated commits with 'refresh goldens' in the message
2. Annotation metadata (_annotation_meta.toml) is updated alongside golden changes

Usage:
    uv run python scripts/check_golden_refresh.py --base origin/main --head HEAD
"""

import argparse
import subprocess
import sys

GOLDEN_PATTERN = "packages/fixtures/sample_documents/"
EXPECTED_SUFFIX = "/expected/"
ANNOTATION_META = "_annotation_meta.toml"


def get_changed_files(base: str, head: str) -> list[str]:
    """Get files changed between base and head."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Fallback: try without merge-base syntax
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            capture_output=True,
            text=True,
            check=False,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_commits_touching_files(base: str, head: str, patterns: list[str]) -> list[dict[str, str]]:
    """Get commits between base..head that touch files matching patterns."""
    result = subprocess.run(
        ["git", "log", "--format=%H|%s", f"{base}..{head}", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    commits: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        sha, subject = line.split("|", 1)
        commits.append({"sha": sha.strip(), "subject": subject.strip()})
    return commits


def is_golden_file(path: str) -> bool:
    """Check if a path is a golden expected file (not annotation meta)."""
    return (
        path.startswith(GOLDEN_PATTERN)
        and EXPECTED_SUFFIX in path
        and not path.endswith(ANNOTATION_META)
        and not path.endswith(".gitkeep")
    )


def is_annotation_meta(path: str) -> bool:
    """Check if a path is an annotation meta file."""
    return path.endswith(ANNOTATION_META) and path.startswith(GOLDEN_PATTERN)


def extract_fixture_id(path: str) -> str:
    """Extract fixture_id from a golden file path."""
    # packages/fixtures/sample_documents/<fixture_id>/expected/...
    parts = path.split("/")
    if len(parts) >= 4:
        return parts[3]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden refresh guard")
    parser.add_argument("--base", required=True, help="Base ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head ref")
    args = parser.parse_args()

    changed = get_changed_files(args.base, args.head)
    golden_files = [f for f in changed if is_golden_file(f)]
    meta_files = [f for f in changed if is_annotation_meta(f)]

    if not golden_files:
        print("No golden fixture files changed. Guard passes.")
        return 0

    print(f"Golden files changed: {len(golden_files)}")
    for gf in golden_files:
        print(f"  {gf}")

    errors: list[str] = []

    # Check 1: commits touching golden files must have 'refresh goldens' in message
    golden_commits = get_commits_touching_files(
        args.base, args.head, [f"{GOLDEN_PATTERN}*/expected/*"]
    )
    for commit in golden_commits:
        if "refresh goldens" not in commit["subject"].lower():
            errors.append(
                f"Commit {commit['sha'][:8]} touches golden files but message "
                f"does not contain 'refresh goldens': {commit['subject']}"
            )

    # Check 2: annotation meta must be updated for each fixture with golden changes
    fixtures_with_golden_changes = {extract_fixture_id(f) for f in golden_files}
    fixtures_with_meta_changes = {extract_fixture_id(f) for f in meta_files}
    for fid in fixtures_with_golden_changes:
        if fid and fid not in fixtures_with_meta_changes:
            errors.append(
                f"Fixture '{fid}': golden files changed but _annotation_meta.toml was not updated"
            )

    if errors:
        print(f"\n{len(errors)} governance violation(s):")
        for err in errors:
            print(f"  BLOCK: {err}")
        print(
            "\nTo fix: place golden changes in dedicated commits with "
            "'refresh goldens' in the message, and update _annotation_meta.toml."
        )
        return 1

    print("Golden refresh governance checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

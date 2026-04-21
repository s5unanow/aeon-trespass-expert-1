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


def _verify_ref_exists(ref: str) -> None:
    """S5U-686: fail-closed if `ref` doesn't resolve to a commit.

    Per .claude/rules/guards.md Rule G1, an unresolvable base or head ref
    (shallow checkout, unfetched remote branch, typo) must NOT silently
    produce an empty diff — it must hard-fail with a clear message.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: cannot resolve ref '{ref}' to a commit.\n"
            "  This usually means the CI checkout is shallow and the ref\n"
            "  is unreachable. Set `fetch-depth: 0` on the\n"
            "  actions/checkout step, or pass --base / --head explicitly.\n"
            f"  git rev-parse stderr: {result.stderr.strip()}"
        )


def get_changed_files(base: str, head: str) -> list[str]:
    """Get files changed between base and head.

    S5U-686: fails closed when BOTH the merge-base diff and the direct diff
    fail. Two-tier fallback is preserved for disjoint-history legitimate
    carve-outs; silent empty-on-failure is removed. Per
    .claude/rules/guards.md Rule G1.
    """
    primary = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if primary.returncode == 0:
        return [line.strip() for line in primary.stdout.splitlines() if line.strip()]
    fallback = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        capture_output=True,
        text=True,
        check=False,
    )
    if fallback.returncode == 0:
        return [line.strip() for line in fallback.stdout.splitlines() if line.strip()]
    raise SystemExit(
        f"ERROR: git diff failed for both '{base}...{head}' and '{base} {head}'.\n"
        f"  primary stderr: {primary.stderr.strip()}\n"
        f"  fallback stderr: {fallback.stderr.strip()}"
    )


def get_commits_touching_files(base: str, head: str, patterns: list[str]) -> list[dict[str, str]]:
    """Get commits between base..head that touch files matching patterns.

    S5U-686: fails closed on non-zero exit from git log — the prior behavior
    (silently returning an empty commit list) converted any ref/diff failure
    into a "no governance violations" guard pass. Per .claude/rules/guards.md
    Rule G1.
    """
    result = subprocess.run(
        ["git", "log", "--format=%H|%s", f"{base}..{head}", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: git log {base}..{head} failed.\n  stderr: {result.stderr.strip()}"
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

    # S5U-686: verify refs BEFORE running diff; shallow checkouts otherwise
    # silently present as "no golden changes" (Rule G1).
    _verify_ref_exists(args.base)
    _verify_ref_exists(args.head)

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

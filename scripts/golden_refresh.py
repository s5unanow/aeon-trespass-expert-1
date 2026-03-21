#!/usr/bin/env python3
"""Guarded golden fixture refresh tool.

Re-computes checksums for a fixture's expected/ files, generates a
machine-readable diff artifact, and optionally updates annotation metadata.

Usage:
    # Preview diff without applying:
    uv run python scripts/golden_refresh.py --fixture walking_skeleton --issue S5U-XXX

    # Apply (update _annotation_meta.toml):
    uv run python scripts/golden_refresh.py --fixture walking_skeleton --issue S5U-XXX --apply
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.eval.fixture_manifest import (
    load_annotation_meta,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "packages" / "fixtures" / "sample_documents"


def get_current_commit_short() -> str:
    """Get the current short commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def compute_expected_checksums(fixture_id: str) -> dict[str, str]:
    """Compute SHA-256 for every JSON file in a fixture's expected/ directory."""
    expected_dir = FIXTURES_DIR / fixture_id / "expected"
    checksums: dict[str, str] = {}
    if not expected_dir.is_dir():
        return checksums
    for path in sorted(expected_dir.glob("*.json")):
        checksums[path.name] = sha256_file(path)
    return checksums


def build_diff(
    old_checksums: dict[str, str],
    new_checksums: dict[str, str],
) -> list[dict[str, str | bool]]:
    """Build per-file diff entries between old and new checksums."""
    all_files = sorted(set(old_checksums) | set(new_checksums))
    entries: list[dict[str, str | bool]] = []
    for filename in all_files:
        old_hash = old_checksums.get(filename, "")
        new_hash = new_checksums.get(filename, "")
        entries.append(
            {
                "filename": filename,
                "old_checksum": old_hash,
                "new_checksum": new_hash,
                "changed": old_hash != new_hash,
                "added": old_hash == "" and new_hash != "",
                "removed": old_hash != "" and new_hash == "",
            }
        )
    return entries


def write_annotation_meta(
    fixture_id: str,
    new_checksums: dict[str, str],
    issue: str,
    reviewer: str,
) -> None:
    """Write updated _annotation_meta.toml for the fixture."""
    meta_path = FIXTURES_DIR / fixture_id / "expected" / "_annotation_meta.toml"
    commit = get_current_commit_short()
    timestamp = datetime.now(tz=UTC).isoformat()

    lines = [
        'schema_version = "annotation_meta.v1"',
        "annotation_format_version = 1",
        f'last_refresh_timestamp = "{timestamp}"',
        f'last_refresh_issue = "{issue}"',
        f'last_refresh_commit = "{commit}"',
        f'reviewer = "{reviewer}"',
        "",
        "[checksums]",
    ]
    for filename in sorted(new_checksums):
        lines.append(f'"{filename}" = "{new_checksums[filename]}"')
    lines.append("")

    meta_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden fixture refresh tool")
    parser.add_argument("--fixture", required=True, help="Fixture ID to refresh")
    parser.add_argument("--issue", required=True, help="Linear issue (e.g. S5U-292)")
    parser.add_argument("--reviewer", default="s5unanow", help="Reviewer handle")
    parser.add_argument("--apply", action="store_true", help="Apply: update annotation meta")
    parser.add_argument("--diff-output", type=Path, help="Write diff artifact JSON to file")
    args = parser.parse_args()

    fixture_dir = FIXTURES_DIR / args.fixture
    if not fixture_dir.is_dir():
        print(f"ERROR: Fixture directory not found: {fixture_dir}")
        return 1

    # Load existing annotation metadata
    try:
        old_meta = load_annotation_meta(args.fixture, repo_root=REPO_ROOT)
        old_checksums = old_meta.checksums
    except FileNotFoundError:
        old_checksums = {}

    # Compute current checksums
    new_checksums = compute_expected_checksums(args.fixture)

    # Build diff
    diff_entries = build_diff(old_checksums, new_checksums)
    changed_count = sum(1 for e in diff_entries if e["changed"])

    # Build artifact
    artifact = {
        "fixture_id": args.fixture,
        "issue": args.issue,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "commit": get_current_commit_short(),
        "files": diff_entries,
        "summary": {
            "total_files": len(diff_entries),
            "changed": changed_count,
            "unchanged": len(diff_entries) - changed_count,
        },
    }

    # Output
    artifact_json = json.dumps(artifact, indent=2)
    print(artifact_json)

    if args.diff_output:
        args.diff_output.write_text(artifact_json, encoding="utf-8")
        print(f"\nDiff artifact written to {args.diff_output}", file=sys.stderr)

    if changed_count == 0:
        print("\nNo changes detected. Annotation metadata is up to date.", file=sys.stderr)
        return 0

    if args.apply:
        write_annotation_meta(args.fixture, new_checksums, args.issue, args.reviewer)
        print(
            f"\nApplied: updated _annotation_meta.toml for '{args.fixture}' "
            f"({changed_count} file(s) changed).",
            file=sys.stderr,
        )
    else:
        print(
            f"\nDry run: {changed_count} file(s) changed. "
            f"Use --apply to update _annotation_meta.toml.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

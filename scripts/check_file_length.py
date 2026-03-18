#!/usr/bin/env python3
"""Check that source files do not exceed a maximum line count.

Usage:
    python scripts/check_file_length.py [--max N] [files...]

If no files are given, scans all Python (apps/pipeline/src, packages/schemas/python,
scripts/) and TypeScript (apps/web/src) source files.

Exit code 0 if all files pass, 1 if any exceed the limit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Files with known violations — each must reference a tracking Linear issue.
KNOWN_VIOLATORS: dict[str, str] = {
    "apps/pipeline/src/atr_pipeline/stages/structure/real_block_builder.py": "S5U-144",
    "scripts/generate_golden_fixtures.py": "S5U-211",
}

DEFAULT_DIRS = [
    "apps/pipeline/src",
    "packages/schemas/python",
    "scripts",
    "apps/web/src",
]

EXTENSIONS = {".py", ".ts", ".tsx"}


def find_source_files(root: Path) -> list[Path]:
    """Find all source files under the default directories."""
    files: list[Path] = []
    for d in DEFAULT_DIRS:
        dirpath = root / d
        if dirpath.exists():
            for ext in EXTENSIONS:
                files.extend(dirpath.rglob(f"*{ext}"))
    return sorted(files)


def check_files(files: list[Path], max_lines: int, root: Path) -> list[str]:
    """Return list of error messages for files exceeding the limit."""
    errors: list[str] = []
    for filepath in files:
        try:
            rel = filepath.relative_to(root)
        except ValueError:
            rel = filepath
        rel_str = str(rel)

        if rel_str in KNOWN_VIOLATORS:
            continue

        line_count = len(filepath.read_text().splitlines())
        if line_count > max_lines:
            errors.append(f"{rel_str}: {line_count} lines (max {max_lines})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check file length limit")
    parser.add_argument("--max", type=int, default=400, help="Maximum lines per file")
    parser.add_argument("files", nargs="*", help="Files to check (default: scan source dirs)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    files = [Path(f).resolve() for f in args.files] if args.files else find_source_files(root)

    errors = check_files(files, args.max, root)
    if errors:
        print(f"Files exceeding {args.max}-line limit:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"All {len(files)} files are within {args.max}-line limit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

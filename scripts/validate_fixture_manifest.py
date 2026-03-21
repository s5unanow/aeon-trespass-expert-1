#!/usr/bin/env python3
"""Validate fixture manifest completeness and checksum integrity.

Checks:
1. Every fixture directory has a manifest entry (and vice versa)
2. Source PDF checksums match
3. Annotation meta files are valid and their checksums match
"""

import sys
import tomllib
from pathlib import Path

from atr_pipeline.eval.fixture_manifest import (
    discover_fixture_dirs,
    load_annotation_meta,
    load_fixture_manifest,
    validate_annotation_checksums,
    validate_manifest_completeness,
    validate_source_checksums,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errors: list[str] = []

    # Load manifest
    try:
        manifest = load_fixture_manifest(repo_root=REPO_ROOT)
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: Cannot load manifest — {e}")
        return 1

    print(f"Loaded manifest: {len(manifest.fixtures)} fixture(s)")

    # Check completeness
    completeness_errors = validate_manifest_completeness(manifest, repo_root=REPO_ROOT)
    errors.extend(completeness_errors)

    # Check source checksums
    checksum_errors = validate_source_checksums(manifest, repo_root=REPO_ROOT)
    errors.extend(checksum_errors)

    # Check annotation metadata for each fixture
    fixture_dirs = discover_fixture_dirs(repo_root=REPO_ROOT)
    for fid in fixture_dirs:
        try:
            meta = load_annotation_meta(fid, repo_root=REPO_ROOT)
        except FileNotFoundError:
            errors.append(f"Fixture '{fid}': missing _annotation_meta.toml")
            continue
        except (ValueError, KeyError, tomllib.TOMLDecodeError) as e:
            errors.append(f"Fixture '{fid}': invalid _annotation_meta.toml — {e}")
            continue

        annotation_errors = validate_annotation_checksums(fid, meta, repo_root=REPO_ROOT)
        errors.extend(annotation_errors)

    # Report
    if errors:
        print(f"\n{len(errors)} error(s):")
        for err in errors:
            print(f"  FAIL: {err}")
        return 1

    print("All fixture manifest checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

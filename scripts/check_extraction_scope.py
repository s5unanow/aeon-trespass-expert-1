#!/usr/bin/env python3
"""Detect extraction-relevant file changes and determine mandatory checks.

Outputs a JSON object for CI integration:
{
  "areas": ["primitive_extraction", "schema"],
  "mandatory_checks": ["unit_tests", "contract_tests", ...],
  "golden_refresh_detected": false,
  "threshold_change_detected": false
}

Usage:
    uv run python scripts/check_extraction_scope.py \\
        --base origin/main --head HEAD --output-json /tmp/scope.json
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

EXTRACTION_PATTERNS: dict[str, list[str]] = {
    "schema": [
        "packages/schemas/python/atr_schemas/native_page_*",
        "packages/schemas/python/atr_schemas/layout_page_*",
        "packages/schemas/python/atr_schemas/page_ir_*",
        "packages/schemas/python/atr_schemas/asset_*",
        "packages/schemas/python/atr_schemas/symbol_*",
        "packages/schemas/python/atr_schemas/page_evidence_*",
        "packages/schemas/python/atr_schemas/resolved_page_*",
    ],
    "primitive_extraction": [
        "apps/pipeline/src/atr_pipeline/stages/extract_native/*",
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/*",
    ],
    "region_order": [
        "apps/pipeline/src/atr_pipeline/stages/structure/reading_order*",
        "apps/pipeline/src/atr_pipeline/stages/structure/region_*",
        "apps/pipeline/src/atr_pipeline/stages/structure/block_builder*",
        "apps/pipeline/src/atr_pipeline/stages/structure/real_block_builder*",
    ],
    "symbol_asset": [
        "apps/pipeline/src/atr_pipeline/stages/symbols/*",
        "packages/schemas/python/atr_schemas/symbol_*",
        "packages/schemas/python/atr_schemas/asset_*",
    ],
    "figure_callout_table": [
        "apps/pipeline/src/atr_pipeline/stages/structure/furniture*",
        "apps/pipeline/src/atr_pipeline/stages/structure/heuristics*",
    ],
    "confidence_routing": [
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/difficulty_*",
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/fallback_*",
        "configs/qa/thresholds*",
    ],
    "golden_fixtures": [
        "packages/fixtures/**/expected/*",
    ],
    "thresholds": [
        "configs/qa/thresholds*",
    ],
}

# Check matrix: area -> mandatory check names
CHECK_MATRIX: dict[str, list[str]] = {
    "schema": ["unit_tests", "contract_tests", "invariant_checker", "codegen_fresh"],
    "primitive_extraction": [
        "unit_tests",
        "contract_tests",
        "invariant_checker",
        "golden_eval",
    ],
    "region_order": [
        "unit_tests",
        "contract_tests",
        "invariant_checker",
        "golden_eval",
    ],
    "symbol_asset": [
        "unit_tests",
        "contract_tests",
        "invariant_checker",
        "golden_eval",
    ],
    "figure_callout_table": [
        "unit_tests",
        "contract_tests",
        "invariant_checker",
        "golden_eval",
        "browser_e2e",
    ],
    "confidence_routing": [
        "unit_tests",
        "contract_tests",
        "invariant_checker",
        "golden_eval",
        "audit_report",
    ],
    "golden_fixtures": ["golden_eval"],
    "thresholds": ["golden_eval", "audit_report"],
}


def get_changed_files(base: str, head: str) -> list[str]:
    """Get files changed between base and head."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            capture_output=True,
            text=True,
            check=False,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def match_areas(changed_files: list[str]) -> set[str]:
    """Determine which extraction areas are affected by changed files."""
    matched: set[str] = set()
    for area, patterns in EXTRACTION_PATTERNS.items():
        for changed in changed_files:
            for pattern in patterns:
                if fnmatch.fnmatch(changed, pattern):
                    matched.add(area)
                    break
    return matched


def compute_mandatory_checks(areas: set[str]) -> list[str]:
    """Compute the union of mandatory checks for all matched areas."""
    checks: set[str] = set()
    for area in areas:
        checks.update(CHECK_MATRIX.get(area, []))
    return sorted(checks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction scope detector")
    parser.add_argument("--base", required=True, help="Base ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head ref")
    parser.add_argument("--output-json", type=Path, help="Write result JSON to file")
    args = parser.parse_args()

    changed = get_changed_files(args.base, args.head)
    areas = match_areas(changed)
    checks = compute_mandatory_checks(areas)

    result = {
        "areas": sorted(areas),
        "mandatory_checks": checks,
        "golden_refresh_detected": "golden_fixtures" in areas,
        "threshold_change_detected": "thresholds" in areas,
    }

    result_json = json.dumps(result, indent=2)
    print(result_json)

    if args.output_json:
        args.output_json.write_text(result_json, encoding="utf-8")
        print(f"\nWritten to {args.output_json}", file=sys.stderr)

    # Set GitHub Actions outputs if running in CI
    gh_out_path = os.environ.get("GITHUB_OUTPUT", "")
    if gh_out_path:
        gh_out = Path(gh_out_path)
        if gh_out.exists():
            golden = "true" if result["golden_refresh_detected"] else "false"
            threshold = "true" if result["threshold_change_detected"] else "false"
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"result={json.dumps(result)}\n")
                f.write(f"golden_refresh_detected={golden}\n")
                f.write(f"threshold_change_detected={threshold}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

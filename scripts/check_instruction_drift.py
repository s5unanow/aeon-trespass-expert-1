#!/usr/bin/env python3
"""Instruction/config drift scanner (S5U-658/667/668/694/727/729/744).

Fails CI when repo instruction files drift from their authoritative source.
Six fail-closed rules (A/B/C/E/F/G) plus one advisory (D):

* Rule A — check-count claim drift vs `.claude/prompts/review.md` max
  numbered item. Structural exemption per S5U-667 (line matches
  `Checks? N[-M] ... (are|always) (run|conditional)`). In
  `_instruction_drift_rule_a.py`.
* Rule B — retired-term references (e.g., "tesseract") unless the file is
  grandfathered (`docs/adrs/**`, `CHANGELOG*`) or a retirement scoping
  marker is within +/-2 lines. In `_instruction_drift_rule_b.py`.
* Rule C — safety-gate scope enumeration in `.claude/skills/**/SKILL.md`
  + `.claude/prompts/**.md` must match CLAUDE.md or defer with
  "per CLAUDE.md" on the same line. In `_instruction_drift_rule_c.py`.
* Rule D — required-check advisory (warning-only, S5U-668). Walks
  `.github/workflows/*.yml` and reports jobs missing from CLAUDE.md §
  Quality gates. Never changes exit code. In `_instruction_drift_rule_d.py`.
* Rule E — CI gate count drift (S5U-694). Ensures CLAUDE.md's CI section
  header ``9 + N extra``, enumerated list max ``L``, and every
  ``all K gates`` claim agree (N = L-8, K = L+1). In
  `_instruction_drift_rule_e.py`.
* Rule F — CI body inline enumeration ban (S5U-729). Forbids mid-line
  ``\\d+\\. `` markers in the CI body so Rule E's line-start regex
  cannot silently miss compressed ``X. ... / Y. ...`` items. In
  `_instruction_drift_rule_f.py`.
* Rule G — CLAUDE.md tilde-fence corpus guard (S5U-744). Forbids active
  tilde fences (``~~~``) in CLAUDE.md because Rule E/F's shared
  ``walk_with_fence_state`` helper does NOT honor them — converts the
  documented S5U-742/S5U-743 asymmetry into a mechanical fail-closed
  signal. In `_instruction_drift_rule_g.py`.

Exit codes: 0 = no drift; 1 = a fail-closed rule violated OR authoritative
source missing/unparseable.

Usage: `python scripts/check_instruction_drift.py [--repo-root PATH]`
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# All five rules live in sibling modules so the main scanner stays under
# the 400-line file-length ceiling. The orchestrator below imports each
# rule's public entry-point and is responsible only for traversal,
# fail-closed coordination, and exit-code arbitration.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _instruction_drift_rule_a import (
    CLAIM_SCAN_SKIP_PATHS,
    compute_authoritative_check_count,
    scan_claim_drift,
)
from _instruction_drift_rule_b import scan_retired_terms
from _instruction_drift_rule_c import (
    CLAUDE_MD,
    extract_canonical_safety_gate_list,
    scan_safety_gate_scope,
)
from _instruction_drift_rule_d import rule_d_advisory
from _instruction_drift_rule_e import scan_ci_gate_claims
from _instruction_drift_rule_f import scan_ci_body_inline_enumeration
from _instruction_drift_rule_g import scan_claude_md_tilde_fences

# --- Paths ---------------------------------------------------------------

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

SCAN_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "artifacts",
        "tmp",
        "_external_reviews",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "__pycache__",
    }
)


# --- Repo traversal -------------------------------------------------------


def iter_markdown_files(repo_root: Path) -> list[Path]:
    """Yield all `*.md` files under repo_root, respecting SCAN_EXCLUDE_DIRS."""
    results: list[Path] = []
    for path in repo_root.rglob("*.md"):
        rel_parts = path.relative_to(repo_root).parts
        if any(part in SCAN_EXCLUDE_DIRS for part in rel_parts):
            continue
        if not path.is_file():
            continue
        results.append(path)
    return sorted(results)


# --- Main -----------------------------------------------------------------


def run(repo_root: Path) -> int:
    """Run all rules and return exit code. 0 = clean, 1 = violations."""
    errors: list[str] = []

    # Fail-closed on authoritative source derivation.
    try:
        expected_count = compute_authoritative_check_count(repo_root)
    except RuntimeError as exc:
        print(f"check_instruction_drift: FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    try:
        canonical_safety_gate = extract_canonical_safety_gate_list(repo_root)
    except RuntimeError as exc:
        print(f"check_instruction_drift: FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1

    # Rule E (S5U-694): CI gate count drift. Reuse claude_md_text for Rule D.
    claude_md_path = repo_root / CLAUDE_MD
    try:
        claude_md_text = claude_md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        claude_md_text = ""
    try:
        errors.extend(scan_ci_gate_claims(claude_md_text))
        errors.extend(scan_ci_body_inline_enumeration(claude_md_text))
    except RuntimeError as exc:
        print(f"check_instruction_drift: FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1

    # Rule G (S5U-744): tilde-fence corpus guard. Does not raise on
    # degenerate inputs — empty CLAUDE.md text returns []. The
    # orchestrator's earlier read failure path already returned 1 above
    # if the file is unreadable.
    errors.extend(scan_claude_md_tilde_fences(claude_md_text))

    md_files = iter_markdown_files(repo_root)

    for path in md_files:
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{rel}: read failed ({exc})")
            continue

        # Rule A
        if rel not in CLAIM_SCAN_SKIP_PATHS:
            errors.extend(scan_claim_drift(Path(rel), text, expected_count))

        # Rule B
        errors.extend(scan_retired_terms(rel, text))

        # Rule C — only applies to skill/prompt files.
        if rel.startswith(".claude/skills/") or rel.startswith(".claude/prompts/"):
            errors.extend(scan_safety_gate_scope(rel, text, canonical_safety_gate))

    # Rule D — warning-only advisory. Runs regardless of A/B/C errors;
    # stdout advisories, stderr warnings, never changes exit code.
    advisories, rule_d_warnings = rule_d_advisory(repo_root, claude_md_text)
    for warning in rule_d_warnings:
        print(f"check_instruction_drift: {warning}", file=sys.stderr)
    for advisory in advisories:
        print(f"check_instruction_drift: {advisory}")

    if errors:
        print(
            "check_instruction_drift: drift detected\n" + "\n".join(errors),
            file=sys.stderr,
        )
        return 1

    print(
        f"check_instruction_drift: OK "
        f"(authoritative review checks: 1-{expected_count}; scanned {len(md_files)} .md files)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
        help="Repo root to scan (defaults to parent of scripts/).",
    )
    args = parser.parse_args()
    return run(args.repo_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

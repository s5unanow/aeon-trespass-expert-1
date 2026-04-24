#!/usr/bin/env python3
"""Instruction/config drift scanner (S5U-658/667/668/694).

Fails CI when repo instruction files drift from their authoritative source.
Four fail-closed rules (A/B/C/E) plus one advisory (D):

* Rule A — check-count claim drift vs `.claude/prompts/review.md` max
  numbered item. Structural exemption per S5U-667 (line matches
  `Checks? N[-M] ... (are|always) (run|conditional)`).
* Rule B — retired-term references (e.g., "tesseract") unless the file is
  grandfathered (`docs/adrs/**`, `CHANGELOG*`) or a retirement scoping
  marker is within +/-2 lines.
* Rule C — safety-gate scope enumeration in `.claude/skills/**/SKILL.md`
  + `.claude/prompts/**.md` must match CLAUDE.md or defer with
  "per CLAUDE.md" on the same line.
* Rule D — required-check advisory (warning-only, S5U-668). Walks
  `.github/workflows/*.yml` and reports jobs missing from CLAUDE.md §
  Quality gates. Never changes exit code. In `_instruction_drift_rule_d.py`.
* Rule E — CI gate count drift (S5U-694). Ensures CLAUDE.md's CI section
  header ``9 + N extra``, enumerated list max ``L``, and every
  ``all K gates`` claim agree (N = L-8, K = L+1). In
  `_instruction_drift_rule_e.py`.

Exit codes: 0 = no drift; 1 = a fail-closed rule violated OR authoritative
source missing/unparseable.

Usage: `python scripts/check_instruction_drift.py [--repo-root PATH]`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Rule D (advisory) and Rule E (CI gate count drift, S5U-694) helpers live
# in sibling modules so the main scanner stays under the 400-line ceiling.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _instruction_drift_rule_d import rule_d_advisory
from _instruction_drift_rule_e import scan_ci_gate_claims

# --- Paths ---------------------------------------------------------------

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

AUTHORITATIVE_REVIEW = Path(".claude/prompts/review.md")
CLAUDE_MD = Path("CLAUDE.md")

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

# Files allowed to name retired terms without scoping. Historical ADRs
# legitimately reference retired tech in context; the scanner itself and
# its tests must name the retired term literally to match on it.
RETIRED_TERM_GRANDFATHERED_PATHS: frozenset[str] = frozenset(
    {
        "scripts/check_instruction_drift.py",
        "apps/pipeline/tests/unit/test_check_instruction_drift.py",
        "tmp/plan-s5u-658.md",
    }
)
RETIRED_TERM_GRANDFATHERED_DIR_PREFIXES: tuple[str, ...] = ("docs/adrs/",)
RETIRED_TERM_GRANDFATHERED_FILE_PREFIXES: tuple[str, ...] = ("CHANGELOG",)

# Rule B: retired terms. Start narrow per issue — grow as the project
# retires more stacks.
RETIRED_TERMS: frozenset[str] = frozenset({"tesseract"})

# Scoping-marker tokens that allow an otherwise-disallowed retired-term
# match. Matched case-insensitively within +/-2 lines of the offending line.
RETIRED_TERM_SCOPING_MARKERS: tuple[str, ...] = (
    "retired",
    "retire",
    "retirement",
)

# --- Authoritative review.md parsing -------------------------------------

_REVIEW_NUMBERED_CHECK_RE = re.compile(r"^(\d+)\.\s+\*\*", re.MULTILINE)


def compute_authoritative_check_count(repo_root: Path) -> int:
    """Parse the top-level numbered check count from review.md.

    Fail-closed: raises if the file is missing or if no numbered checks
    are parsed (prevents silent fail-open on an empty or refactored file).
    """
    path = repo_root / AUTHORITATIVE_REVIEW
    if not path.is_file():
        raise RuntimeError(
            f"Authoritative review file missing: {AUTHORITATIVE_REVIEW}. "
            "Cannot derive authoritative check count."
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    numbers = [int(m.group(1)) for m in _REVIEW_NUMBERED_CHECK_RE.finditer(text)]
    if not numbers:
        raise RuntimeError(
            f"No numbered checks parsed from {AUTHORITATIVE_REVIEW}. "
            "Pattern `^\\d+\\. \\*\\*` matched zero items."
        )
    return max(numbers)


# --- Rule A: claim drift --------------------------------------------------

# Both hyphen-minus and EN DASH (U+2013). Case-insensitive.
_CLAIM_RANGE_RE = re.compile(
    r"checks?\s+1\s*[-\u2013]\s*(\d+)",
    re.IGNORECASE,
)
_CLAIM_ALL_RE = re.compile(
    r"all\s+(\d+)\s+checks?\b",
    re.IGNORECASE,
)

# Skip claim-scan inside these files — they legitimately reference
# historical / adversarial counts (e.g., test fixtures, ADR history).
CLAIM_SCAN_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "scripts/check_instruction_drift.py",
        "apps/pipeline/tests/unit/test_check_instruction_drift.py",
        "tmp/plan-s5u-658.md",
    }
)

# Structural sub-range exemption (S5U-667). A line is exempt from Rule A
# only if its structural form matches the template
# `Checks? <N>[-<en-dash>]<M>(, <K>)* (and <K>)? (are|always) (run|conditional)`.
# Prose lines that merely contain "trigger" / "conditional" / "always run"
# somewhere else are NOT exempt (pre-S5U-667 substring match was the bypass).
# See `tmp/plan-s5u-667-s5u-668.md` §4b for the equivalence-class matrix.
_STRUCTURAL_SUBRANGE_RE = re.compile(
    r"""
    ^\s*                              # leading whitespace
    (?:[-*+]\s+)?                     # optional bullet marker + whitespace
    Checks?\s+                        # "Check" or "Checks"
    \d+\s*[-\u2013]\s*\d+             # N-M (hyphen-minus or en-dash)
    (?:\s*,\s*\d+)*                   # optional ", K" repeats
    (?:\s*,?\s*and\s+\d+)?            # optional "and K" / ", and K"
    \s+(?:are|always)\s+(?:run|conditional)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_inside_backticks_or_quotes(line: str, start: int, end: int) -> bool:
    """Return True if chars [start:end] of `line` are enclosed by backticks,
    single quotes, or double quotes. This treats the claim as an *example*
    (documenting the regex/quote), not a live count claim.
    """
    for quote in ("`", '"', "'"):
        # Count quote occurrences in line[:start]. If odd, we are currently
        # inside a quoted span.
        if line.count(quote, 0, start) % 2 == 1 and quote in line[end:]:
            return True
    return False


def _line_is_structural_subrange(line: str) -> bool:
    """True if `line` or any sentence segment (split on ``.;:``) matches the
    structural sub-range template. Anchored at segment start so prose prefixes
    like "When a trigger fires, walk checks 1-21" don't match.
    """
    if _STRUCTURAL_SUBRANGE_RE.match(line):
        return True
    return any(_STRUCTURAL_SUBRANGE_RE.match(seg) for seg in re.split(r"[.;:]", line))


def _claim_scan_file(path: Path, text: str, expected: int) -> list[str]:
    """Return a list of drift messages for the file, empty if clean."""
    msgs: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Sub-range context (S5U-667): line matches the structural sub-range
        # template. Exempt only when the line's form is "Checks N-M ...
        # are/always run/conditional"; prose that merely contains those
        # keywords does not match.
        if _line_is_structural_subrange(line):
            continue
        for regex in (_CLAIM_RANGE_RE, _CLAIM_ALL_RE):
            for m in regex.finditer(line):
                if _is_inside_backticks_or_quotes(line, m.start(), m.end()):
                    continue
                claimed = int(m.group(1))
                if claimed != expected:
                    msgs.append(
                        f"{path}:{lineno}: claim '{m.group(0)}' says {claimed}, "
                        f"authoritative count is {expected}"
                    )
    return msgs


# --- Rule B: retired terms ------------------------------------------------


def _is_retired_term_grandfathered(rel_path: str) -> bool:
    if rel_path in RETIRED_TERM_GRANDFATHERED_PATHS:
        return True
    if any(rel_path.startswith(p) for p in RETIRED_TERM_GRANDFATHERED_DIR_PREFIXES):
        return True
    fname = Path(rel_path).name
    return any(fname.startswith(p) for p in RETIRED_TERM_GRANDFATHERED_FILE_PREFIXES)


def _has_scoping_marker(lines: list[str], idx: int, window: int = 2) -> bool:
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    joined = " ".join(lines[lo:hi]).lower()
    return any(marker in joined for marker in RETIRED_TERM_SCOPING_MARKERS)


def _retired_term_scan_file(rel_path: str, text: str) -> list[str]:
    if _is_retired_term_grandfathered(rel_path):
        return []
    msgs: list[str] = []
    lines = text.splitlines()
    for term in RETIRED_TERMS:
        term_re = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        for idx, line in enumerate(lines):
            if term_re.search(line):
                if _has_scoping_marker(lines, idx):
                    continue
                msgs.append(
                    f"{rel_path}:{idx + 1}: retired term '{term}' mentioned "
                    f"without nearby retirement scoping marker"
                )
    return msgs


# --- Rule C: safety-gate scope enumeration consistency -------------------

_SAFETY_GATE_PARENTHETICAL_RE = re.compile(
    r"safety-gate\s+scope\s*\(([^)]*)\)",
    re.IGNORECASE,
)


def _extract_canonical_safety_gate_list(repo_root: Path) -> str:
    """Return the canonical safety-gate-scope parenthetical from CLAUDE.md.

    Fail-closed: raises if CLAUDE.md is missing or no parenthetical is found.
    """
    path = repo_root / CLAUDE_MD
    if not path.is_file():
        raise RuntimeError(f"CLAUDE.md missing at repo root: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _SAFETY_GATE_PARENTHETICAL_RE.search(text)
    if m is None:
        raise RuntimeError(
            "Canonical 'safety-gate scope (...)' not found in CLAUDE.md. "
            "Cannot derive canonical enumeration."
        )
    return m.group(1).strip()


def _safety_gate_scan_file(
    rel_path: str,
    text: str,
    canonical: str,
) -> list[str]:
    """Check that any 'safety-gate scope (...)' in this file either matches
    canonical or the line also says 'per CLAUDE.md'."""
    msgs: list[str] = []
    for idx, line in enumerate(text.splitlines()):
        for m in _SAFETY_GATE_PARENTHETICAL_RE.finditer(line):
            found = m.group(1).strip()
            if found == canonical:
                continue
            if "per CLAUDE.md" in line:
                continue
            msgs.append(
                f"{rel_path}:{idx + 1}: 'safety-gate scope ({found})' does not "
                f"match canonical CLAUDE.md enumeration and does not defer with "
                f"'per CLAUDE.md'. Canonical: '{canonical}'"
            )
    return msgs


# Rules D (advisory) and E (CI gate count) live in sibling modules; see
# their module docstrings for semantics.


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
        canonical_safety_gate = _extract_canonical_safety_gate_list(repo_root)
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
    except RuntimeError as exc:
        print(f"check_instruction_drift: FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1

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
            errors.extend(_claim_scan_file(Path(rel), text, expected_count))

        # Rule B
        errors.extend(_retired_term_scan_file(rel, text))

        # Rule C — only applies to skill/prompt files.
        if rel.startswith(".claude/skills/") or rel.startswith(".claude/prompts/"):
            errors.extend(_safety_gate_scan_file(rel, text, canonical_safety_gate))

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

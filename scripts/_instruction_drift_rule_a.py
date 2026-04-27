"""Rule A (check-count claim drift) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-668 established the same pattern for Rule D,
S5U-694 for Rule E, and S5U-727 completes the split for A/B/C).

## What Rule A protects

CLAUDE.md and adjacent instruction files cite the number of reviewer
checks defined in ``.claude/prompts/review.md``. Whenever a new check
lands in review.md, every "checks 1-N" / "all N checks" claim across
the repo must be bumped to match the new max. Pre-S5U-658 those drifted
silently.

The authoritative count is the max numbered top-level item in
``review.md``. Rule A scans every ``*.md`` file (sans the skip-list)
for "checks 1-N" / "all N checks" claims and flags any whose N differs
from the authoritative count.

## Structural sub-range exemption (S5U-667)

A line whose form is ``Checks N-M ... (are|always) (run|conditional)``
is a structural sub-range — not a total-count claim — and is exempt.
Pre-S5U-667, the exemption was an unbounded substring match on the
words "trigger" / "conditional" / "always run" anywhere on the line,
which was bypassable via prose. The post-S5U-667 form is anchored at
segment start so prose prefixes ("When the trigger fires, walk checks
1-21") do not match.

## Backtick / quote exemption

A claim enclosed in backticks (``` `checks 1-21` ```) or paired single /
double quotes is treated as a quoted *example* (documenting the
regex/quote), not a live count claim. This lets the scanner's own
docstring legitimately reference example claim text without flagging
itself.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **review.md missing** — `compute_authoritative_check_count` raises
  `RuntimeError`. Fail-closed.
- **review.md present but no numbered items** — raises `RuntimeError`.
  Fail-closed (an empty count would silently pass every claim).
"""

from __future__ import annotations

import re
from pathlib import Path

AUTHORITATIVE_REVIEW = Path(".claude/prompts/review.md")

# Skip claim-scan inside these files — they legitimately reference
# historical / adversarial counts (e.g., test fixtures, ADR history).
CLAIM_SCAN_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "scripts/check_instruction_drift.py",
        "apps/pipeline/tests/unit/test_check_instruction_drift.py",
        "tmp/plan-s5u-658.md",
    }
)

_REVIEW_NUMBERED_CHECK_RE = re.compile(r"^(\d+)\.\s+\*\*", re.MULTILINE)

# Both hyphen-minus and EN DASH (U+2013). Case-insensitive.
_CLAIM_RANGE_RE = re.compile(
    r"checks?\s+1\s*[-\u2013]\s*(\d+)",
    re.IGNORECASE,
)
_CLAIM_ALL_RE = re.compile(
    r"all\s+(\d+)\s+checks?\b",
    re.IGNORECASE,
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


def scan_claim_drift(path: Path, text: str, expected: int) -> list[str]:
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

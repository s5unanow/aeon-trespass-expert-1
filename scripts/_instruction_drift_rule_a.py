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

## Structural sub-range exemption (S5U-667 + S5U-676)

A segment whose form is ``Checks N-M ... (are|always) (run|conditional)``
is a structural sub-range — not a total-count claim — and is exempt.
Pre-S5U-667, the exemption was an unbounded substring match on the
words "trigger" / "conditional" / "always run" anywhere on the line,
which was bypassable via prose.

S5U-667 anchored the structural regex at segment start so prose prefixes
("When the trigger fires, walk checks 1-21") no longer match. But the
S5U-667 helper exempted the whole line if **any** ``.;:``-separated
segment matched, which produced a fresh bypass class: a stale claim in
segment 1 with a structural template in segment 2 (e.g.,
``When a new trigger fires, walk checks 1-21: Checks 1-13 always run.``)
slipped through.

S5U-676 fixes this by scanning each segment **independently**: a line is
split on ``.;:`` and each segment is scanned for claims. Only segments
matching the structural template are exempt; the rest are claim-scanned.
The structural regex is also anchored at segment end (``\\s*$``) so a
prose continuation after the structural prefix (``Checks 1-13 always
run, but walk checks 1-21 in edge cases``) no longer prefix-matches.

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

# Structural sub-range exemption (S5U-667, end-anchored S5U-676). A
# segment is exempt from Rule A only if its structural form matches
# `Checks? <N>[-<en-dash>]<M>(, <K>)* (and <K>)? (are|always) (run|conditional)`
# AND the segment ends after `(run|conditional)` (modulo trailing whitespace).
# Prose continuations like
# "Checks 1-13 always run, but walk checks 1-21 in edge cases" no longer
# prefix-match. Pre-S5U-676 the helper exempted the whole line if any
# segment matched, which let a stale claim in segment 1 + structural
# template in segment 2 bypass Rule A.
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
    \s*$                              # end-anchor: no prose continuation
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Sentence-segment splitter for per-segment scanning (S5U-676). Pre-S5U-676
# the helper exempted the whole line if any segment matched the structural
# template; the new contract scans each segment independently, exempting
# only segments whose form matches. Comma is intentionally NOT a splitter
# — the end-anchored _STRUCTURAL_SUBRANGE_RE catches the comma-continuation
# case directly, and adding `,` would over-fragment legitimate enumerations
# like "Checks 1-3, 5, 7 are run".
_SEGMENT_SPLITTER_RE = re.compile(r"[.;:]")


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


def _segment_spans(line: str) -> list[tuple[int, int]]:
    """Return ``[(start, end), ...]`` spans (in original-line offsets) of
    each segment after splitting `line` on ``[.;:]``. Empty trailing segments
    are preserved so callers can decide whether to skip them.

    Used by `scan_claim_drift` to scan each segment independently while
    keeping the backtick-exemption check operating on original-line offsets
    (the helper counts quotes against the unmodified line).
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for m in _SEGMENT_SPLITTER_RE.finditer(line):
        spans.append((cursor, m.start()))
        cursor = m.end()
    spans.append((cursor, len(line)))
    return spans


def _segment_is_structural_subrange(segment: str) -> bool:
    """True if the (already-split) segment matches the structural template.

    The regex is anchored at both segment start and segment end (S5U-676),
    so prose prefixes ("When a trigger fires, walk checks 1-21") and prose
    continuations ("Checks 1-13 always run, but walk checks 1-21") both
    fall through to claim-scanning.
    """
    return bool(_STRUCTURAL_SUBRANGE_RE.match(segment))


def scan_claim_drift(path: Path, text: str, expected: int) -> list[str]:
    """Return a list of drift messages for the file, empty if clean.

    Per-segment scanning (S5U-676): each line is split on ``[.;:]`` and
    each segment is scanned independently. Only segments whose form matches
    the structural sub-range template are exempt; the rest are claim-scanned.
    Backtick / quote exemption operates on the original-line offsets.
    """
    msgs: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for seg_start, seg_end in _segment_spans(line):
            segment = line[seg_start:seg_end]
            if _segment_is_structural_subrange(segment):
                continue
            for regex in (_CLAIM_RANGE_RE, _CLAIM_ALL_RE):
                for m in regex.finditer(segment):
                    # Translate segment-relative offsets to line-relative
                    # offsets so the backtick / quote exemption operates
                    # on the original line.
                    line_start = seg_start + m.start()
                    line_end = seg_start + m.end()
                    if _is_inside_backticks_or_quotes(line, line_start, line_end):
                        continue
                    claimed = int(m.group(1))
                    if claimed != expected:
                        msgs.append(
                            f"{path}:{lineno}: claim '{m.group(0)}' says {claimed}, "
                            f"authoritative count is {expected}"
                        )
    return msgs

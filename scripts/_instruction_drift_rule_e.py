"""Rule E (CI gate count drift) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-658 established the same pattern for Rule D).

## What Rule E protects

CLAUDE.md carries three interlocking claims about the CI gate count:

1. A section header ``### CI (GitHub Actions, 9 + N extra) …`` — claims
   there are ``9`` local gates plus ``N`` additional CI gates.
2. A numbered enumeration directly below that header (items ``9.``, ``10.``
   …, ``L.``) listing each CI-extra gate. The max item number ``L`` is
   the ground truth for how many gates exist.
3. One or more ``all K gates`` summary claims elsewhere in the file.

These three must agree: ``N == L - 8`` (the header's extras count matches
the enumeration) and ``K == L + 1`` for every ``all K gates`` mention
(total gates = 9 local + ``L - 8`` extras = ``L + 1``).

S5U-690 added a new CI-extra (`check_make_doc_parity.py` as item 17) but
did not bump the three claims; S5U-694 fixes that and installs this
guard to prevent recurrence of the drift class.

## Why CLAUDE.md's enumeration is the authoritative source

Workflow YAML (``.github/workflows/*.yml``) is not a viable count source:

- Steps include checkout, setup, dependency install — not gates.
- Jobs don't map 1:1 to gates: ``check_instruction_drift.py`` and
  ``check_make_doc_parity.py`` both live inside the ``python / test``
  job's step list. Two gates, one job.

The enumerated list in CLAUDE.md *is* the schema: the worker bumps it
each time a new gate lands. This rule enforces the three claims it
backstops stay aligned.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **CLAUDE.md missing** — the caller (`check_instruction_drift.run`)
  already fails closed via `_extract_canonical_safety_gate_list`. Rule E
  receives text that is guaranteed non-empty but may be arbitrary.
- **CI section header missing** — `RuntimeError`. Fail-closed.
- **Enumerated list empty** — `RuntimeError`. Fail-closed (an empty list
  would silently pass the parity check).
- **Header N parses as non-integer** — regex requires ``\\d+``; if no match,
  header missing → handled above.
- **No ``all K gates`` match** — NOT an error; the phrase may legitimately
  not appear. Rule E only validates matches it finds.

## Known limitation (documented, intentional)

- The max-item-number approach does not detect *gaps* (e.g., items
  ``9,10,11,12,14,15,16,17`` — missing 13). Fixing this requires
  validating sequence contiguity, which is out of scope for this rule
  and would need its own fixture suite. A gap is a weird state the
  reviewer would likely catch; the ``all K gates`` claim would also
  disagree if the author believed the count was the gap-including
  number.

## Sibling guard (Rule F, S5U-729)

The line-start anchor on `_NUMBERED_ITEM_RE` makes Rule E silently miss
inline markers like ``11. foo / 12. bar`` on a single line. Rule F
(`_instruction_drift_rule_f.py`) closes that convention by forbidding
the compressed shape in CLAUDE.md's CI body. Rule F reuses
`_ci_section_body` here so the two rules read the same body slice.
"""

from __future__ import annotations

import re

# Header: "### CI (GitHub Actions, 9 + N extra)" on its own line.
# Captures N. Case-insensitive on "CI" / "GitHub"; whitespace-tolerant.
_CI_HEADER_RE = re.compile(
    r"^###\s+CI\s*\(GitHub\s+Actions,\s*9\s*\+\s*(\d+)\s*extra\)",
    re.IGNORECASE | re.MULTILINE,
)

# Numbered list items at the start of a line. Matches "9. ", "10. ", etc.
# Only scanned within the CI section body (between the header and the
# next ``## `` / ``### `` heading).
_NUMBERED_ITEM_RE = re.compile(r"^(\d+)\.\s+", re.MULTILINE)

# "all K gates" / "all K gate" summary claim. Case-insensitive; requires
# word boundary so "Install 5 gates" or similar don't match. We anchor on
# the literal word "all" to keep scope tight — this is the phrasing
# CLAUDE.md currently uses in both "CI green" claims.
_ALL_K_GATES_RE = re.compile(
    r"\ball\s+(\d+)\s+gates?\b",
    re.IGNORECASE,
)


def _ci_section_body(text: str) -> tuple[str, int, int]:
    """Return (body, header_line_number, header_n_claimed).

    The body is the slice of text starting right after the header line and
    ending at the next ``## `` / ``### `` heading **outside any fenced code
    block**, or end of file. The ``header_line_number`` is 1-indexed and
    points at the line containing the CI header. ``header_n_claimed`` is
    the integer parsed out of ``9 + N extra``.

    Raises ``RuntimeError`` if the header is absent.

    Fence-aware termination (S5U-742): a ``## `` / ``### `` line inside a
    fenced code block (delimited by ``\\`\\`\\``) does NOT terminate the
    slice. Rule F's existing fence detector toggles on the same delimiter;
    keeping the convention symmetric across the two modules. Tilde fences
    (``~~~``) are intentionally NOT honored — Rule F doesn't honor them
    either, and CLAUDE.md does not use them. If a future edit introduces
    them, both modules must be extended in lockstep. An unclosed fence
    leaves the walker in ``in_fence=True`` state and the slice runs to
    EOF — same soft-limit convention Rule F documents.
    """
    match = _CI_HEADER_RE.search(text)
    if match is None:
        raise RuntimeError(
            "CLAUDE.md: CI section header '### CI (GitHub Actions, 9 + N extra) …' "
            "not found. Cannot derive authoritative CI gate count."
        )
    header_start = match.start()
    header_line_number = text.count("\n", 0, header_start) + 1
    # Body starts right after the header line's newline.
    body_newline = text.find("\n", match.end())
    body_start = len(text) if body_newline == -1 else body_newline + 1

    # Walk the body line-by-line tracking fence state. Stop only at a
    # heading-shaped line OUTSIDE any fence.
    in_fence = False
    body_end = len(text)
    cursor = body_start
    for line in text[body_start:].splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^#{2,3}\s+", line):
            body_end = cursor
            break
        cursor += len(line)
    return text[body_start:body_end], header_line_number, int(match.group(1))


def _max_enumerated_item(body: str) -> int:
    """Return the max numbered-list item index (``L``) in ``body``.

    Raises ``RuntimeError`` if no numbered items are present.
    """
    numbers = [int(m.group(1)) for m in _NUMBERED_ITEM_RE.finditer(body)]
    if not numbers:
        raise RuntimeError(
            "CLAUDE.md: CI section has no numbered enumeration (``^\\d+\\. ``). "
            "Cannot derive authoritative CI gate count."
        )
    return max(numbers)


def scan_ci_gate_claims(text: str) -> list[str]:
    """Return a list of drift messages for the CI gate count claims.

    Empty list = clean. Each message names the offending CLAUDE.md line
    and the computed-vs-claimed values.

    Raises ``RuntimeError`` on fail-closed inputs (missing header, empty
    enumeration).
    """
    body, header_line, header_n_claimed = _ci_section_body(text)
    max_item = _max_enumerated_item(body)
    expected_extras = max_item - 8  # items 0-8 are the 9 local gates
    expected_total = max_item + 1

    msgs: list[str] = []
    if header_n_claimed != expected_extras:
        msgs.append(
            f"CLAUDE.md:{header_line}: CI section header claims '9 + "
            f"{header_n_claimed} extra' but enumeration reaches item "
            f"{max_item} (→ '9 + {expected_extras} extra')"
        )

    # Every "all K gates" claim must equal expected_total. Iterate with
    # line numbers so each offending match is named.
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _ALL_K_GATES_RE.finditer(line):
            k_claimed = int(m.group(1))
            if k_claimed != expected_total:
                msgs.append(
                    f"CLAUDE.md:{lineno}: claim '{m.group(0)}' says "
                    f"{k_claimed}, CI enumeration implies {expected_total} "
                    f"(9 local + {expected_extras} extras)"
                )
    return msgs

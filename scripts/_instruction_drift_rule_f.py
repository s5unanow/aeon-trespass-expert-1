"""Rule F (CI body inline enumeration ban) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-668 established the same pattern for Rule D,
S5U-694 for Rule E, and S5U-727 split A/B/C; this completes the family
with F per S5U-729).

## What Rule F protects

Rule E (`_instruction_drift_rule_e.py`) derives the authoritative CI gate
count from the max line-start `\\d+\\. ` marker in CLAUDE.md's CI section
body. The regex is anchored on line-start under ``re.MULTILINE``, so any
numbered marker that lives mid-line is invisible to Rule E.

Concrete failure mode (live precedent for S5U-729): CLAUDE.md once carried
``11. `check_extraction_scope.py` / 12. `check_golden_refresh.py` — ...``
on one line. Rule E saw ``11`` but not ``12``. The failure was silent
because ``max`` happened to coincide with the right total (item ``12``
was below ``max=17``), but a future compression of items 16/17 onto one
line would silently shift the authoritative count from 17 to 16 and
let an internally-consistent-but-wrong claim set pass.

Rule F enforces the structural convention: **every numbered gate entry in
the CI section body MUST start a new line**. Compressing
``X. ... / Y. ...`` onto one line is forbidden.

## Scope

Rule F reads the same CI section body that Rule E does — it imports
`_ci_section_body` from the Rule E module so the two rules stay in
lockstep on what counts as "the CI body." Markers outside the CI body
(other ``## ``/``### `` sections, prose elsewhere in CLAUDE.md, code
blocks fenced with ``\\`\\`\\``) are out of scope.

## Detection

Per-line walk of the CI body. For each non-fenced line:

- Strip leading whitespace (indented sub-list items are legal).
- The line must *start* with a ``\\d+\\. `` marker — i.e., the line is
  itself a list item Rule E sees. Prose lines that do not start with a
  numbered marker are out of scope.
- Within a list-item line, look for a ``\\d+\\. `` marker that is
  preceded by a list-compression separator (``/``, ``,``, or the word
  ``and``). This is the ``11. foo / 12. bar`` shape — the only
  documented compression vocabulary the rule has to defend against.

Why a separator-based pattern instead of "any second ``\\d+\\. `` on the
line": prose periods inside list-item bodies (e.g., ``Rule G1.``,
``PR #307.``, sentence-ending periods) frequently produce ``\\d+\\. ``
tokens that are not list-item markers. The separator-based pattern fires
on the compression vocabulary specifically.

Trade-off: a future, exotic compression like ``11. foo; 12. bar``
(semicolon separator) or ``11. foo: 12. bar`` (colon) would slip past
Rule F. These are not documented compression shapes; if a worker
introduces one, the appropriate response is to extend the separator
set, not to weaken the regex.

Code-fence-tracking: lines starting with ``\\`\\`\\`` toggle a fence flag;
content inside a fenced code block is skipped (so a bash snippet
referencing ``step 12.`` in the CI body does not false-positive). An
unclosed fence is a documented soft limit — the walker stays in
"inside-fence" mode and could mask later violations, but a malformed
fence would be caught by other lints.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **CLAUDE.md missing / CI header missing** — `_ci_section_body` raises
  `RuntimeError`. The orchestrator's existing fail-closed `except`
  block (the same one wrapping Rule E) catches it.
- **CI body present but empty** — empty body, no markers, returns `[]`.
  Legitimate scan target (matches Rule E's "empty body" handling — Rule E
  raises in this case via `_max_enumerated_item`, which fires *before*
  Rule F in the orchestrator).
- **Body contains only inline markers, no line-start ones** —
  `_max_enumerated_item` would raise first (Rule E), so Rule F never
  runs on this shape under the orchestrator's call order. As a unit
  function it would still flag every offending line.

## Why content-derived (G2)

Rule F walks the body content and detects mid-line markers from
structure, not from a hardcoded list of "lines to check." A renamed
gate, a new gate, or any other content edit is scanned automatically.
"""

from __future__ import annotations

import re

from _instruction_drift_rule_e import _ci_section_body

# Line-start (post-leading-whitespace) marker: this line IS a Rule E list
# item. Used to scope Rule F to lines Rule E reads.
_LINE_START_MARKER_RE = re.compile(r"^\d+\.\s")
# Compression-vocabulary inline marker: a `\d+\. ` preceded by a list-
# compression separator (`/`, `,`, or the word `and`) with intervening
# whitespace. Catches `11. foo / 12. bar`, `11. foo, 12. bar`, and
# `11. foo and 12. bar`. Does NOT catch prose periods inside list bodies
# (e.g., `Rule G1.`, sentence-ending `307.`).
_COMPRESSION_MARKER_RE = re.compile(r"(?:[/,]|\band\b)\s+(\d+)\.\s")


def scan_ci_body_inline_enumeration(text: str) -> list[str]:
    """Return drift messages for compressed `X. ... / Y. ...` shapes in the CI body.

    Empty list = clean. Each message names the offending CLAUDE.md line and
    the inline marker(s) found.

    Only fires on lines whose *stripped* form starts with a `\\d+\\. ` marker
    (i.e., list-item lines Rule E reads) AND that contain a `\\d+\\. ` mid-
    line preceded by a list-compression separator (`/`, `,`, or `and`).
    Prose periods inside a list body (e.g., "Rule G1.", "PR #307.") are
    out of scope.

    Raises ``RuntimeError`` only if `_ci_section_body` raises (missing CI
    header) — same fail-closed contract as Rule E's body extraction.
    """
    body, header_line, _ = _ci_section_body(text)
    msgs: list[str] = []
    in_fence = False

    # Walk the body line by line. `splitlines()` discards the trailing
    # newline; we count lines starting at the first body line, which is
    # `header_line + 1` in CLAUDE.md.
    for offset, line in enumerate(body.splitlines()):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not _LINE_START_MARKER_RE.match(stripped):
            # Not a list-item line — Rule E does not read its numbers,
            # Rule F has nothing to say.
            continue
        compressed = list(_COMPRESSION_MARKER_RE.finditer(stripped))
        if not compressed:
            continue
        marker_text = ", ".join(f"'{m.group(1)}.'" for m in compressed)
        line_no = header_line + 1 + offset
        msgs.append(
            f"CLAUDE.md:{line_no}: CI body list-item line compresses inline "
            f"numbered marker(s) {marker_text} via a list separator (/, ,, "
            f"or 'and') — Rule E's line-start regex would silently miss "
            f"them. Split onto separate lines."
        )
    return msgs

"""Rule G (CLAUDE.md tilde-fence corpus guard) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-668/694/727/729 established the same pattern for
Rules D/E/F).

## What Rule G protects

Rule E (`_instruction_drift_rule_e.py`) and Rule F
(`_instruction_drift_rule_f.py`) share a fence-length-aware walker
(`walk_with_fence_state`, S5U-743) that intentionally does NOT honor tilde
fences (``~~~``). The asymmetry is documented in the walker's docstring at
``scripts/_instruction_drift_rule_e.py::walk_with_fence_state docstring``: tildes were left out
because CLAUDE.md does not currently use them, and tracking both fence
flavors symmetrically is heavier than the current threat justifies.

The asymmetry is currently INERT — ``grep "~~~" CLAUDE.md`` returns
nothing. But a single future CLAUDE.md edit that introduces a tilde-fenced
block silently re-opens the S5U-742 bypass class:

- Rule E's ``_ci_section_body`` slice would terminate at any ``## ``/``### ``
  heading inside the tilde fence (the walker treats those lines as plain
  content because it does not see the fence).
- Rule F's mid-line scan would never see compressed
  ``\\d+\\. ... / \\d+\\. ...`` markers below the tilde fence (because the
  slice already terminated above).

S5U-744 converts the documented asymmetry into a mechanical fail-closed
guard: any ``~~~`` line in CLAUDE.md (outside a backtick fence — i.e., as
active markdown) fires a drift message naming the line and pointing at
S5U-744's two-option remediation: (1) split the content out of the tilde
fence into separate sections, or (2) extend ``walk_with_fence_state`` to
honor ``~~~`` symmetrically and remove this guard.

## Scope

Rule G scans CLAUDE.md only. Other ``*.md`` files are out of scope — Rule
E/F do not consume them, so a tilde fence elsewhere does not bypass the
gates Rule G is protecting.

A tilde-fence-shaped line INSIDE a backtick code block (``\\`\\`\\``-fenced)
is content, not active markdown. Rule G uses the shared
``walk_with_fence_state`` helper from Rule E to skip those lines —
otherwise documenting the asymmetry would be self-defeating (a sample
``~~~`` snippet inside a ``\\`\\`\\``-fenced example would always fire).

## Detection

Per-line walk of CLAUDE.md text. For each line where the walker reports
``in_fence=False`` (i.e., not inside a backtick fence):

- Strip up to 3 leading spaces (CommonMark §4.5: a fence may be indented
  ≤3 spaces).
- The line must start with a run of ≥3 ``~`` characters (the CommonMark
  minimum fence width).

Each match fires a drift message naming the line and S5U-744.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **CLAUDE.md missing** — handled by the orchestrator's earlier fail-
  closed `extract_canonical_safety_gate_list` call (Rule C). Rule G
  receives whatever string the orchestrator passes; if that string is
  empty, Rule G returns ``[]`` legitimately (an empty file has no tildes).
- **CLAUDE.md unreadable as UTF-8** — the orchestrator reads with
  ``errors="replace"``, so Rule G sees a string. Replacement chars do
  not match ``~``.
- **Walker raises** — the shared walker does not raise; `walk_with_fence_state`
  is a pure generator over ``splitlines(keepends=True)``.

## Why content-derived (G2)

Rule G derives the blocked set from CONTENT — every line whose stripped
form matches ``^~{3,}``. There is no hardcoded list of "tilde patterns
to ban" — any ≥3-tilde fence at line start (post-leading-whitespace) is
in scope. Rename / wrapper / alias adversarial inputs covered:

- ``~~~`` (3 tildes) — minimum fence width.
- ``~~~~`` / ``~~~~~`` — longer fences (CommonMark allows ≥3).
- ``~~~markdown`` / ``~~~bash`` / etc. — info-string variants.
- 1-3 leading spaces (CommonMark indent allowance).

Out of scope by design (not an evasion):

- ``~`` / ``~~`` — CommonMark requires ≥3; not a fence.
- ``~~~`` mid-line (e.g., inside prose) — CommonMark requires line-start
  position; not a fence.
- ``~~~`` inside a backtick-fenced code block — content, not active
  markdown; the walker skips it.

## Remediation message

When Rule G fires, the message names CLAUDE.md:line and points at the
two paths forward:

1. Restructure the section to avoid the tilde fence (cheapest — convert
   to a backtick fence, or move the content out of CLAUDE.md if it was
   only there for documentation).
2. Extend ``walk_with_fence_state`` (and any callers depending on its
   docstring) to honor ``~~~`` symmetrically with ``\\`\\`\\``, remove
   this Rule G guard, and update the asymmetry sentinel test in
   ``test_check_instruction_drift_s5u744.py``. Per S5U-744, this is the
   "heavier option" — only worth the surface-area cost if a future
   CLAUDE.md edit genuinely needs tilde fences for content that can't
   be expressed otherwise.
"""

from __future__ import annotations

import re

from _instruction_drift_rule_e import walk_with_fence_state

# Tilde fence at line start (post-leading-whitespace ≤3 chars). CommonMark
# §4.5 requires ≥3 same-character fence chars; we match `~{3,}` so longer
# fences (4+, 5+) are also caught. The leading-space allowance is `[ ]{0,3}`
# per CommonMark indent rule. The pattern is applied to the line's stripped
# form (`line.lstrip()`) so any indentation up to the CommonMark allowance
# (and beyond — Rule F's caller is similarly tolerant of over-indentation,
# matching its existing convention) matches.
_TILDE_FENCE_RE = re.compile(r"^~{3,}")


def scan_claude_md_tilde_fences(text: str) -> list[str]:
    """Return drift messages for active tilde fences (``~~~``) in CLAUDE.md.

    Empty list = clean. Each message names the offending CLAUDE.md line
    and the S5U-744 remediation paths.

    The walker (`walk_with_fence_state` from Rule E) is used to skip
    lines INSIDE a backtick code block — a tilde-shaped line inside a
    ``\\`\\`\\```-fenced example is content, not an active fence, and
    must not false-positive.

    Does not raise on degenerate inputs: an empty string returns ``[]``
    legitimately. Missing-file / fail-closed is handled by the
    orchestrator before Rule G runs (see Rule C's
    ``extract_canonical_safety_gate_list``).
    """
    msgs: list[str] = []
    for lineno, (line_with_nl, in_fence) in enumerate(walk_with_fence_state(text), start=1):
        if in_fence:
            # Inside a backtick fence — tilde-shaped content is not an
            # active markdown fence. Skip.
            continue
        line = line_with_nl.rstrip("\n")
        stripped = line.lstrip()
        # Re-check leading-space count: a line with >3 leading spaces is
        # NOT a CommonMark fence per §4.5 (it's an indented code block).
        # We allow ≤3 leading spaces.
        leading_spaces = len(line) - len(line.lstrip(" "))
        if leading_spaces > 3:
            continue
        if _TILDE_FENCE_RE.match(stripped):
            msgs.append(
                f"CLAUDE.md:{lineno}: tilde fence (`~~~`) detected. Rule E/F's "
                f"shared `walk_with_fence_state` helper does NOT honor tilde "
                f"fences (per the `walk_with_fence_state` docstring in "
                f"`scripts/_instruction_drift_rule_e.py`); content inside "
                f"this fence is invisible to the asymmetry-aware slice and "
                f"bypasses both rules. Remediation: (1) restructure to avoid "
                f"the tilde fence (convert to a backtick fence or move the "
                f"content out of CLAUDE.md), or (2) extend "
                f"`walk_with_fence_state` to honor `~~~` symmetrically and "
                f"remove this Rule G guard along with the S5U-744 sentinel "
                f"test. See S5U-744."
            )
    return msgs

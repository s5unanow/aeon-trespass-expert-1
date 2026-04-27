"""Rule B (retired-term references) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-668 established the same pattern for Rule D,
S5U-694 for Rule E, and S5U-727 completes the split for A/B/C).

## What Rule B protects

When a tech stack is retired (e.g., Tesseract was retired per S5U-592),
the repo carries that decision forward via instruction files
(CLAUDE.md, ADRs, READMEs). New worker agents should not silently
re-introduce the retired stack into the codebase via fresh `*.md`
mentions that lack a retirement scoping marker — the cheap path for a
worker is to re-suggest a tool the project already discarded.

Rule B scans every `*.md` file (sans grandfathered paths) for case-
insensitive whole-word matches of any token in `RETIRED_TERMS`. A match
is exempt if a scoping-marker token (`retired` / `retire` / `retirement`)
appears within ±2 lines of the match.

## Grandfathered paths

- `docs/adrs/**` — ADRs legitimately reference retired tech in context.
- `CHANGELOG*` — release notes name what was removed.
- The scanner itself (`scripts/check_instruction_drift.py`) and its
  tests must literally name the retired term to match on it.
- `tmp/plan-s5u-658.md` — original planning doc.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **Empty `text`** — no matches; empty result list. Not a degenerate
  *input* — an empty file is a legitimate scan target.
- **Non-UTF-8 file** — caller decodes with `errors="replace"` before
  calling; this module operates on already-decoded text.
- **Zero retired terms** — would silently pass every `.md` file. The
  current `RETIRED_TERMS` set is non-empty (`{"tesseract"}`); this is
  not a fail-closed concern because adding a retired term is the
  rule's *intent*, not bypass surface.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def scan_retired_terms(rel_path: str, text: str) -> list[str]:
    """Return a list of retired-term-drift messages for the file, empty if clean."""
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

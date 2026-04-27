"""Rule C (safety-gate scope enumeration) helpers for check_instruction_drift.py.

Extracted to a sibling module so the main scanner stays under the 400-line
file-length ceiling (S5U-668 established the same pattern for Rule D,
S5U-694 for Rule E, and S5U-727 completes the split for A/B/C).

## What Rule C protects

CLAUDE.md carries a canonical "safety-gate scope (...)" parenthetical
enumerating which surfaces require coordinator-orchestrated review (hooks,
pre-commit checks, review gates, CI checks, merge guards, branch-
protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits).

Skill files (`.claude/skills/**/SKILL.md`) and prompt files
(`.claude/prompts/**.md`) frequently re-cite that enumeration. Rule C
enforces that any cited form either (a) matches CLAUDE.md byte-for-byte
or (b) defers with the literal token "per CLAUDE.md" on the same line.

A skill that says "safety-gate scope (hooks, CI checks)" without
deferring is silent drift — the skill author trimmed the list and now a
worker following that skill will under-escalate.

## Degenerate inputs (per `.claude/rules/guards.md` G1)

- **CLAUDE.md missing** — `extract_canonical_safety_gate_list` raises
  `RuntimeError`. Fail-closed.
- **CLAUDE.md present but no canonical parenthetical** — raises
  `RuntimeError`. Fail-closed (an unfindable canonical would silently
  pass every cited form).
- **File has no `safety-gate scope` mention** — empty result list.
  Legitimate scan target.
"""

from __future__ import annotations

import re
from pathlib import Path

CLAUDE_MD = Path("CLAUDE.md")

_SAFETY_GATE_PARENTHETICAL_RE = re.compile(
    r"safety-gate\s+scope\s*\(([^)]*)\)",
    re.IGNORECASE,
)


def extract_canonical_safety_gate_list(repo_root: Path) -> str:
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


def scan_safety_gate_scope(
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

"""Makefile gate-wiring invariants (S5U-1231).

These tests pin the real repo ``Makefile`` so the gate composition cannot
silently drift:

1. ``make lint`` must invoke ``scripts/check_instruction_drift.py`` and must do
   so fail-closed (no ``|| true``, no leading ``-`` recipe prefix) so a drift
   failure aborts ``make lint`` non-zero — the local-green ⇄ CI-green parity the
   issue restores for ``*.md`` edits.
2. ``make check`` must aggregate exactly ``lint``, ``typecheck`` and ``test`` —
   not a silent subset that could pass locally while CI is red.
3. ``check`` must be declared ``.PHONY`` (it is not a file target).

This is config-invariant coverage of the Makefile this PR edits; there is no
production code path to exercise, so the assertions read the Makefile directly.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MAKEFILE = REPO / "Makefile"


def _target_recipe_lines(text: str, target: str) -> list[str]:
    """Return the TAB-indented recipe lines of ``target`` (excluding comments).

    A GNU make recipe is the run of TAB-prefixed lines following the target
    header, terminated by the first line that is non-empty and not TAB-indented.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_target = False
    header_re = re.compile(rf"^{re.escape(target)}\s*:")
    for line in lines:
        if not in_target:
            if header_re.match(line):
                in_target = True
            continue
        if line and not line.startswith("\t"):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


def _target_prerequisites(text: str, target: str) -> set[str]:
    """Return the prerequisite tokens declared on ``target:``'s header line."""
    for line in text.splitlines():
        m = re.match(rf"^{re.escape(target)}\s*:\s*(.*)$", line)
        if m:
            rhs = m.group(1)
            # Strip an inline ``## help`` comment if present.
            rhs = rhs.split("##", 1)[0]
            return {tok for tok in rhs.split() if tok}
    raise AssertionError(f"Makefile target {target!r} not found")


def test_make_lint_invokes_instruction_drift_fail_closed() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    recipe = _target_recipe_lines(text, "lint")
    drift_lines = [ln for ln in recipe if "check_instruction_drift.py" in ln]
    assert drift_lines, (
        f"make lint must invoke scripts/check_instruction_drift.py (recipe was: {recipe})"
    )
    for ln in drift_lines:
        # Fail-closed: the invocation must not swallow its exit code.
        assert "||" not in ln, f"instruction-drift line swallows failure: {ln!r}"
        assert not ln.startswith("-"), f"instruction-drift line ignores errors (-prefix): {ln!r}"


def test_make_check_aggregates_lint_typecheck_test() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    prereqs = _target_prerequisites(text, "check")
    assert prereqs == {"lint", "typecheck", "test"}, (
        "make check must aggregate exactly {lint, typecheck, test} (no silent "
        f"subset); got {prereqs}"
    )


def test_check_target_is_phony() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    phony_targets: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^\.PHONY\s*:\s*(.*)$", line)
        if m:
            phony_targets.update(m.group(1).split())
    assert "check" in phony_targets, "make check must be declared .PHONY"

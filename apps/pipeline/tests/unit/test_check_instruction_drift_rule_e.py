"""Tests for Rule E (CI gate count drift) — S5U-694.

Rule E protects against drift between three interlocking claims in
CLAUDE.md:

- ``### CI (GitHub Actions, 9 + N extra)`` header
- the numbered enumeration below it (items 9..L)
- every ``all K gates`` claim elsewhere in the file

Authoritative source: the max numbered item ``L`` in the CI section's
enumeration. Required: ``N == L - 8`` and ``K == L + 1``.

Red-before evidence: all synthetic tests in this file exercise Rule E
against hand-built fixtures. Rule E's functions
(``scan_ci_gate_claims``, sibling module ``_instruction_drift_rule_e``)
do not exist in pre-fix code — an import at pre-fix SHA fails. For the
CLAUDE.md drift specifically, commit f0dcd4fd166148096d8b5de5199cba90e5ffdd36
(branch base / main HEAD pre-fix) contains the drifted phrases
``9 + 7 extra`` / ``all 16 gates`` with enumeration reaching item 16;
running Rule E against that CLAUDE.md produces a drift message naming
those lines. See tmp/plan-s5u-694.md §5.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_instruction_drift.py"
# Add scripts/ to sys.path so the sibling module can be imported directly.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _instruction_drift_rule_e import scan_ci_gate_claims  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests — exercise scan_ci_gate_claims directly.
# ---------------------------------------------------------------------------


def _claude_md_fixture(header_n: int, max_item: int, all_k: list[int] | None = None) -> str:
    """Assemble a synthetic CLAUDE.md excerpt with the CI section.

    The fixture places items starting at 9 so the section resembles the
    real CLAUDE.md (items 0-8 are local gates documented separately).
    ``all_k`` seeds the number of ``all K gates`` claims and their
    values.
    """
    items = "\n".join(f"{n}. `gate-{n}` — description" for n in range(9, max_item + 1))
    tail_claims = ""
    if all_k:
        tail_claims = "\n\n## Tail\n\n" + "\n".join(f"- all {k} gates pass" for k in all_k)
    return (
        "# CLAUDE.md\n\n"
        "## Quality gates\n\n"
        "### Local (pre-commit hook, 9 checks: 1 secret guard + 8 quality gates)\n\n"
        "0. secret guard\n"
        f"### CI (GitHub Actions, 9 + {header_n} extra) — runs …\n\n"
        f"{items}\n"
        f"{tail_claims}\n"
    )


def test_happy_path_all_three_agree() -> None:
    """Header N=9, enumeration reaches 17, all claims say 18. No drift."""
    fixture = _claude_md_fixture(header_n=9, max_item=17, all_k=[18, 18])
    assert scan_ci_gate_claims(fixture) == []


def test_header_vs_enumeration_mismatch() -> None:
    """Enumeration reaches 17 but header claims '9 + 7 extra' → drift."""
    fixture = _claude_md_fixture(header_n=7, max_item=17)
    msgs = scan_ci_gate_claims(fixture)
    assert len(msgs) == 1
    assert "claims '9 + 7 extra'" in msgs[0]
    assert "reaches item 17" in msgs[0]
    assert "9 + 9 extra" in msgs[0]


def test_all_k_gates_single_mismatch() -> None:
    """Enumeration 17, header 9, but 'all 17 gates' → 1 drift message."""
    fixture = _claude_md_fixture(header_n=9, max_item=17, all_k=[17])
    msgs = scan_ci_gate_claims(fixture)
    assert len(msgs) == 1
    assert "'all 17 gates'" in msgs[0]
    assert "says 17" in msgs[0]
    assert "implies 18" in msgs[0]


def test_all_k_gates_mixed_values() -> None:
    """Two 'all K gates' occurrences — one right, one wrong. Only wrong flagged."""
    fixture = _claude_md_fixture(header_n=9, max_item=17, all_k=[18, 16])
    msgs = scan_ci_gate_claims(fixture)
    assert len(msgs) == 1
    assert "'all 16 gates'" in msgs[0]


def test_all_k_gates_both_mismatched() -> None:
    """Both occurrences wrong — both flagged."""
    fixture = _claude_md_fixture(header_n=9, max_item=17, all_k=[16, 17])
    msgs = scan_ci_gate_claims(fixture)
    assert len(msgs) == 2


def test_adversarial_internally_consistent_stale_count() -> None:
    """Known limitation: guard cannot catch a case where header/enum/claims
    all agree internally but contradict external reality (workflow adds a new
    gate, enumerator/header/claim all still on old count). Documented as a
    non-goal in the Rule E module docstring — that's a human-review surface.
    """
    # header_n=7, max_item=15 → expected_extras=7, matches → no drift.
    # all_k=[16], expected_total=16 → matches → no drift.
    fixture = _claude_md_fixture(header_n=7, max_item=15, all_k=[16])
    assert scan_ci_gate_claims(fixture) == []


def test_missing_ci_header_raises() -> None:
    """G1: missing CI section header fails closed."""
    fixture = "# CLAUDE.md\n\nno CI header anywhere\n"
    with pytest.raises(RuntimeError, match="CI section header"):
        scan_ci_gate_claims(fixture)


def test_empty_enumeration_raises() -> None:
    """G1: CI header present but zero numbered items fails closed."""
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 0 extra) — …\n\n"
        "Just prose with no numbered items.\n"
    )
    with pytest.raises(RuntimeError, match="no numbered enumeration"):
        scan_ci_gate_claims(fixture)


def test_enumeration_continues_into_next_section_ignored() -> None:
    """Numbered items only inside the CI body count; a later ## heading truncates."""
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 2 extra) — …\n\n"
        "9. first\n"
        "10. second\n"
        "\n"
        "## Other section\n\n"
        "99. red-herring in another section\n"
    )
    # max=10, header_n=2, L-8=2 → no drift. 99 is in a different section.
    assert scan_ci_gate_claims(fixture) == []


def test_case_insensitive_header_match() -> None:
    """Header matches case-insensitively (defensive)."""
    fixture = "# CLAUDE.md\n\n### ci (gitHub Actions, 9 + 1 extra) — …\n\n9. one\n"
    assert scan_ci_gate_claims(fixture) == []


def test_non_gate_k_not_flagged() -> None:
    """'All 3 gates pass for local' is a literal match; but 'all 42 seconds' is not."""
    fixture = _claude_md_fixture(header_n=1, max_item=9, all_k=None)
    fixture += "\nSome prose about all 42 seconds of waiting.\n"
    # No 'all K gates' pattern in the prose, so nothing flagged.
    assert scan_ci_gate_claims(fixture) == []


# ---------------------------------------------------------------------------
# Integration — run the real CLI against the live CLAUDE.md.
# ---------------------------------------------------------------------------


def test_real_claude_md_is_clean_after_fix(tmp_path: Path) -> None:
    """Run the real check_instruction_drift.py against the repo root.

    After this PR's CLAUDE.md edits land, the scanner exits 0 — proving
    Rule E accepts the fixed content. Pre-fix (commit
    f0dcd4fd166148096d8b5de5199cba90e5ffdd36), this test fails with a
    drift message naming the '9 + 7 extra' header line and the two
    'all 16 gates' lines.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"check_instruction_drift exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_rule_e_catches_pre_fix_shape(tmp_path: Path) -> None:
    """Feed the scanner a synthetic CLAUDE.md matching the pre-S5U-694 drift
    shape (header 9+7, enumeration to 17, 'all 16 gates'). Expect exit 1 and
    drift messages on the header and the gates claim.

    This doubles as a red-before demonstration for Rule E's integration:
    the synthetic fixture mirrors commit
    f0dcd4fd166148096d8b5de5199cba90e5ffdd36's CLAUDE.md at the CI section.
    """
    # Build a pre-fix-shaped CLAUDE.md with the safety-gate scope
    # parenthetical + review-md-compatible numbered-check marker so the
    # upstream fail-closed paths don't trip first.
    review_md = tmp_path / ".claude" / "prompts" / "review.md"
    review_md.parent.mkdir(parents=True, exist_ok=True)
    review_md.write_text("1. **x**\n2. **y**\n", encoding="utf-8")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# CLAUDE.md\n\n"
        "Any safety-gate scope (hooks, review gates) should …\n\n"
        "### CI (GitHub Actions, 9 + 7 extra) — runs …\n\n"
        + "\n".join(f"{n}. gate-{n}" for n in range(9, 18))
        + "\n\n- all 16 gates pass — required for merge.\n"
        "- all 16 gates — local green alone is not sufficient.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "9 + 7 extra" in combined
    assert "reaches item 17" in combined
    assert "'all 16 gates'" in combined

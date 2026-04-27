"""Tests for Rule F (CI body inline enumeration ban) — S5U-729.

Rule F protects Rule E by forbidding compressed ``X. ... / Y. ...`` shapes
on a single line in CLAUDE.md's CI section. Rule E's count-derivation
regex anchors on line-start under ``re.MULTILINE``, so any inline marker
preceded by a list separator (``/``, ``,``, or ``and``) is invisible to
Rule E. Rule F closes the convention.

## Red-before evidence

The Rule F module (`scripts/_instruction_drift_rule_f.py`) does not exist
in pre-fix code. At commit ff008fd875a790fe23584aafbe5534774c5df9a0
(branch base / current main HEAD pre-PR), running

    python -c "import sys; sys.path.insert(0, 'scripts'); \\
               import _instruction_drift_rule_f"

fails with ``ModuleNotFoundError: No module named '_instruction_drift_rule_f'``.
Every test in this file imports that module at collection time and would
fail to collect at the cited SHA. Additionally, the integration test
``test_real_claude_md_is_clean_after_fix`` exercises the orchestrator
against the live (un-compressed) CLAUDE.md; pre-fix the orchestrator
exits 0 but for the wrong reason (no Rule F), and the synthetic
compressed-shape test exits 0 pre-fix (Rule F missing) and exits 1 post-fix.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_instruction_drift.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _instruction_drift_rule_e import _ci_section_body, scan_ci_gate_claims  # noqa: E402
from _instruction_drift_rule_f import scan_ci_body_inline_enumeration  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests — exercise scan_ci_body_inline_enumeration directly.
# ---------------------------------------------------------------------------


def _ci_fixture(items: str, header_n: int = 1) -> str:
    """Assemble a synthetic CLAUDE.md excerpt with the CI section.

    ``items`` is the raw enumeration body (allows hand-crafted compressed
    or fenced shapes). ``header_n`` seeds the header's "9 + N extra"
    claim — Rule F doesn't read it but the orchestrator's Rule E does
    when these fixtures are passed through the CLI; unit tests against
    Rule F alone ignore it.
    """
    return (
        "# CLAUDE.md\n\n"
        "## Quality gates\n\n"
        f"### CI (GitHub Actions, 9 + {header_n} extra) — runs …\n\n"
        f"{items}\n"
    )


def test_happy_path_all_line_start_enumeration_returns_empty() -> None:
    """All numbered items at line start: no compression, no drift."""
    body = "9. first\n10. second\n11. third\n"
    fixture = _ci_fixture(body, header_n=3)
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_compressed_slash_separator_flags_line() -> None:
    """The live S5U-729 precedent: ``11. foo / 12. bar`` on one line."""
    body = (
        "9. one\n10. two\n"
        "11. `check_extraction_scope.py` / 12. `check_golden_refresh.py` — CI-only\n"
    )
    fixture = _ci_fixture(body, header_n=4)
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1
    assert "'12.'" in msgs[0]
    assert "Split onto separate lines" in msgs[0]


def test_compressed_comma_separator_flags_line() -> None:
    """``11. foo, 12. bar`` shape — comma-separated compression."""
    body = "9. a\n11. foo, 12. bar\n"
    fixture = _ci_fixture(body, header_n=3)
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1
    assert "'12.'" in msgs[0]


def test_compressed_and_separator_flags_line() -> None:
    """``11. foo and 12. bar`` shape — word-`and` compression."""
    body = "9. a\n11. foo and 12. bar\n"
    fixture = _ci_fixture(body, header_n=3)
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1
    assert "'12.'" in msgs[0]


def test_prose_period_in_list_body_does_not_flag() -> None:
    """``Rule G1.`` and ``PR #307.`` inside a list-item body are prose,
    not list markers, and must not flag.
    """
    # Live shape from CLAUDE.md:59 (post-S5U-690).
    body = (
        "9. a\n"
        "17. `check_make_doc_parity.py` — fails CI when `make lint` "
        "drifts. Fail-closed per `.claude/rules/guards.md` Rule G1. "
        "Runs inside `python / test` (S5U-690, PR #307).\n"
    )
    fixture = _ci_fixture(body, header_n=9)
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_prose_line_not_starting_with_marker_is_ignored() -> None:
    """A prose line that contains ``11. ... / 12.`` but is not a list-
    item line (does not start with ``\\d+\\. ``) is out of scope. Rule E
    does not read its numbers either.
    """
    body = "9. one\nThis prose mentions item 11. / 12. as examples.\n"
    fixture = _ci_fixture(body, header_n=1)
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_indented_sub_list_item_is_legal() -> None:
    """An indented sub-list item like ``   12. sub-step`` is allowed."""
    body = "9. parent\n   12. sub-step\n10. next-parent\n"
    fixture = _ci_fixture(body, header_n=2)
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_code_block_inside_ci_body_is_skipped() -> None:
    """Fenced code blocks must not be scanned. A bash snippet referencing
    ``step 12.`` mid-line inside a fence is invisible to Rule F.
    """
    body = "9. one\n10. two\n```bash\necho 'step 11. and 12. compressed for demo'\n```\n"
    fixture = _ci_fixture(body, header_n=2)
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_two_compressed_lines_both_flag() -> None:
    """Two separate lines with compression — both flagged independently."""
    body = "9. one\n10. two\n11. foo / 12. bar\n13. baz, 14. qux\n"
    fixture = _ci_fixture(body, header_n=6)
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 2


def test_multiple_inline_markers_on_one_line_listed() -> None:
    """If three items are compressed onto one line (``11. a / 12. b / 13. c``),
    both inline markers (``12.`` and ``13.``) are listed in the message.
    """
    body = "9. one\n11. a / 12. b / 13. c\n"
    fixture = _ci_fixture(body, header_n=5)
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1
    assert "'12.'" in msgs[0]
    assert "'13.'" in msgs[0]


def test_marker_outside_ci_body_ignored() -> None:
    """Mid-line compression in a different ``## ``/``### `` section is
    out of scope — Rule F only reads the CI body slice.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — …\n\n"
        "9. clean\n"
        "\n"
        "## Other section\n\n"
        "11. foo / 12. bar\n"
    )
    assert scan_ci_body_inline_enumeration(fixture) == []


def test_g1_missing_ci_header_raises() -> None:
    """G1: missing CI section header propagates the same RuntimeError
    Rule E raises (Rule F reuses ``_ci_section_body``).
    """
    fixture = "# CLAUDE.md\n\nno CI header anywhere\n"
    with pytest.raises(RuntimeError, match="CI section header"):
        scan_ci_body_inline_enumeration(fixture)


# ---------------------------------------------------------------------------
# Integration — run the real CLI against the live CLAUDE.md.
# ---------------------------------------------------------------------------


def test_real_claude_md_is_clean_after_fix() -> None:
    """After this PR's CLAUDE.md edits land, the scanner exits 0 against
    the real repo — proving Rule F accepts the un-compressed content.
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


def test_orchestrator_flags_compressed_shape(tmp_path: Path) -> None:
    """Synthetic CLAUDE.md with the live S5U-729 compression shape causes
    the orchestrator to exit 1 with a Rule F message.
    """
    review_md = tmp_path / ".claude" / "prompts" / "review.md"
    review_md.parent.mkdir(parents=True, exist_ok=True)
    review_md.write_text("1. **x**\n2. **y**\n", encoding="utf-8")

    claude_md = tmp_path / "CLAUDE.md"
    # Intentionally craft a fully-consistent fixture: header `9 + 9 extra`,
    # max line-start item 17, all 18 gates. Rule E sees no drift. Only
    # Rule F should fire on the compressed line.
    claude_md.write_text(
        "# CLAUDE.md\n\n"
        "Any safety-gate scope (hooks, review gates) should …\n\n"
        "### CI (GitHub Actions, 9 + 9 extra) — runs …\n\n"
        "9. a\n10. b\n"
        "11. `check_extraction_scope.py` / 12. `check_golden_refresh.py` — CI-only\n"
        "13. c\n14. d\n15. e\n16. f\n17. g\n"
        "\n- all 18 gates pass — required for merge.\n",
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
    assert "compresses inline numbered marker" in combined
    assert "'12.'" in combined


# ---------------------------------------------------------------------------
# Fence-aware slice termination (S5U-742) — `_ci_section_body` must skip
# `## ` / `### ` heading-shaped lines when they live inside a fenced code
# block. Pre-S5U-742 the regex was fence-blind, so an in-fence pseudo-
# heading silently truncated the slice and hid every numbered item below
# the fence from both Rule E and Rule F.
# ---------------------------------------------------------------------------


def _ci_fixture_with_fenced_heading(in_fence_heading: str, post_fence_lines: str) -> str:
    """Build a CLAUDE.md fixture where a heading-shaped line lives inside a
    fenced code block in the CI body, followed by additional list-item lines
    that the slice MUST include after the fix.
    """
    return (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "Example template:\n\n"
        "```markdown\n"
        f"{in_fence_heading}\n"
        "- example bullets\n"
        "```\n\n"
        f"{post_fence_lines}\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )


def test_ci_body_slice_skips_fenced_h3_heading() -> None:
    """Scenario A: a `### ` line inside a fenced code block must NOT
    terminate the body slice. Post-fix, lines after the fence (incl. real
    list items) appear in the slice.
    """
    fixture = _ci_fixture_with_fenced_heading(
        in_fence_heading="### Section header in example",
        post_fence_lines="10. real-gate-a\n11. real-gate-b",
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. real-gate-a" in body, (
        f"Body slice should include real list items after a fenced pseudo-heading; got: {body!r}"
    )
    assert "11. real-gate-b" in body
    # Real next section is OUTSIDE the CI body — must terminate slice.
    assert "Real next section" not in body
    assert "## Real next section" not in body


def test_ci_body_slice_skips_fenced_h2_heading() -> None:
    """Scenario B: a `## ` line inside a fenced code block must NOT
    terminate the body slice (same property as h3 — both Rule E and Rule F
    consume the slice and lose visibility otherwise).
    """
    fixture = _ci_fixture_with_fenced_heading(
        in_fence_heading="## Pseudo-h2 inside fence",
        post_fence_lines="10. real-gate-a\n11. real-gate-b",
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. real-gate-a" in body
    assert "11. real-gate-b" in body
    assert "Real next section" not in body


def test_ci_body_slice_terminates_on_outside_heading() -> None:
    """Scenario C (regression): a real `### ` heading OUTSIDE any fence
    still terminates the slice. Guards against over-correction in the fix
    that would let real headings through.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n"
        "10. extra\n"
        "\n"
        "### Subsequent real section\n\n"
        "11. should-NOT-be-in-slice\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. extra" in body
    assert "Subsequent real section" not in body
    assert "should-NOT-be-in-slice" not in body


def test_ci_body_slice_unclosed_fence_runs_to_eof() -> None:
    """Scenario F: an unclosed fence (no closing ` ``` `) keeps the walker
    in `in_fence=True` state and the slice runs to EOF. This matches Rule
    F's documented soft-limit convention — an unclosed fence is itself a
    malformed-CLAUDE.md signal that surfaces elsewhere; it must not silently
    drop content.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "```markdown\n"
        "### unclosed fence — heading-shaped line inside\n"
        "10. trailing-after-fenced-heading-no-close\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. trailing-after-fenced-heading-no-close" in body, (
        f"Unclosed fence should not truncate slice; got: {body!r}"
    )


def test_rule_f_catches_compressed_marker_below_fenced_heading() -> None:
    """Adversarial fixture from S5U-742 'Evidence' section: a fenced code
    block in the CI body contains an `### ` line. Pre-S5U-742, the slice
    terminates there and Rule F never sees the compressed
    `10. ... / 11. ...` line below the fence. Post-fix Rule F sees and
    flags it.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "Example template:\n\n"
        "```markdown\n"
        "### Section header in example\n"
        "- bullets\n"
        "```\n\n"
        "10. real-gate-a / 11. compressed-and-invisible\n"
        "\n- all 10 gates pass — required for merge.\n"
    )
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1, f"expected one Rule F drift message; got {msgs!r}"
    assert "'11.'" in msgs[0]
    assert "Split onto separate lines" in msgs[0]


def test_rule_e_catches_drift_below_fenced_heading() -> None:
    """Same adversarial shape as the Rule F test, but exercise Rule E's
    count derivation: with the fence properly skipped, the max line-start
    item is 12 (not 9), and the `all 10 gates` claim is now drift.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 3 extra) — runs\n\n"
        "9. local-only\n\n"
        "Example template:\n\n"
        "```markdown\n"
        "### Section header in example\n"
        "- bullets\n"
        "```\n\n"
        "10. real-gate-a\n"
        "11. real-gate-b\n"
        "12. real-gate-c\n"
        "\n- all 10 gates pass — required for merge.\n"
    )
    msgs = scan_ci_gate_claims(fixture)
    # max=12, expected_extras = 12-8 = 4, header claims 3 → drift.
    # expected_total = 13, claim "all 10 gates" → drift.
    assert any("9 + 3 extra" in m for m in msgs), msgs
    assert any("'all 10 gates'" in m for m in msgs), msgs

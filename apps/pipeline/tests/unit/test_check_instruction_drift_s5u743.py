"""Tests for S5U-743 — fence-length-aware walker for Rule E/F slice termination.

Pre-S5U-743 the walker in ``_ci_section_body`` (and Rule F's matching per-line
walker) toggled ``in_fence`` on any line whose ``lstrip()`` started with
three or more backticks. CommonMark §4.5 requires that a fence opened with
N backticks closes only on a line whose first non-whitespace run is ≥N
backticks of the same character AND whose post-run content is whitespace-
only (no info-string). The length-blind toggle mis-tracked the canonical
CommonMark idiom — wrap an example with 4 backticks so the inner 3-backtick
fence is content — and silently truncated the slice at any heading-shaped
line below the inner 3-backtick fence. Rule F went silent on compressed
markers; Rule E still fired on header/all-K mismatches but with a misleading
message.

This file's tests live separate from ``test_check_instruction_drift_rule_f.py``
to keep both files under the 400-line ceiling enforced by
``scripts/check_file_length.py``. The S5U-742 fence-aware tests stay in the
Rule F file (their slot of origin); S5U-743 generalizes that fix to fence
LENGTHS and lives here.

## Red-before evidence

At commit 79e1e26ae88c31dd737eecd558b8fdd5957a7290 (branch base / current
``main`` HEAD pre-fix), running

    uv run pytest apps/pipeline/tests/unit/test_check_instruction_drift_s5u743.py -v

produces six failures (the regression sentinel ``test_open3_close4_still_closes``
already passes pre-fix because ``ticks=4 >= fence_len=3`` is coincidentally
satisfied by the old length-blind toggle for that specific input). Failure
excerpts captured in the commit message.

After applying the fence-length-aware walker (``walk_with_fence_state`` in
``_instruction_drift_rule_e.py`` + Rule F switching to it), all seven tests
pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _instruction_drift_rule_e import _ci_section_body, scan_ci_gate_claims  # noqa: E402
from _instruction_drift_rule_f import scan_ci_body_inline_enumeration  # noqa: E402

# ---------------------------------------------------------------------------
# Fence-length-aware walker (S5U-743) — `_ci_section_body` and Rule F's
# body walker must honor CommonMark §4.5: a fence opened with N backticks
# closes only on a line whose first run is ≥N backticks of the same
# character AND whose post-run content is whitespace-only (no info-string).
# Pre-S5U-743 the walker toggled `in_fence` on any ```-prefixed line, so
# the canonical CommonMark idiom — wrap an example with 4 backticks so the
# inner 3-backtick fence is content — was mis-tracked: the 3-backtick line
# was treated as a close, then any heading-shaped line inside the wrapper
# terminated the slice.
# ---------------------------------------------------------------------------


def test_ci_body_slice_skips_4backtick_wrapper_with_3backtick_inner() -> None:
    """Scenario 1 (the canonical idiom): a 4-backtick wrapper containing a
    3-backtick block with `### ` inside. Pre-fix the inner ``` was treated
    as a close, then the `### ` line terminated the slice — lines after the
    wrapper were lost. Post-fix the wrapper stays open until a ≥4-backtick
    closing fence and the slice includes the post-wrapper list items.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 4 extra) — runs\n\n"
        "9. local-only\n\n"
        "````markdown\n"
        "Here is how to write a fenced code block in markdown:\n\n"
        "```python\n"
        "### inside python block\n"
        "def foo(): pass\n"
        "```\n\n"
        "End of code-block-in-docs example.\n"
        "````\n\n"
        "10. real-gate-a\n"
        "11. real-gate-b\n"
        "12. real-gate-c\n"
        "13. real-gate-d\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. real-gate-a" in body, (
        f"4-backtick wrapper must not be closed by inner 3-backtick fence; got: {body!r}"
    )
    assert "11. real-gate-b" in body
    assert "12. real-gate-c" in body
    assert "13. real-gate-d" in body
    # Real next section must still terminate the slice.
    assert "Real next section" not in body


def test_rule_f_catches_compressed_below_4backtick_wrapper() -> None:
    """Scenario 1 + Rule F: a compressed `13. ... / 14. ...` line BELOW the
    4-backtick wrapper must be flagged. Pre-fix the wrapper was pseudo-
    closed by the inner 3-backtick fence and the `### ` line truncated the
    slice, so Rule F never saw the compressed line.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 5 extra) — runs\n\n"
        "9. local-only\n\n"
        "````markdown\n"
        "```python\n"
        "### inside python block\n"
        "```\n"
        "````\n\n"
        "10. real-gate\n"
        "11. real-gate\n"
        "12. real-gate\n"
        "13. compressed-real-gate / 14. another-compressed\n"
        "\n- all 15 gates pass — required for merge.\n"
    )
    msgs = scan_ci_body_inline_enumeration(fixture)
    assert len(msgs) == 1, f"expected one Rule F drift message; got {msgs!r}"
    assert "'14.'" in msgs[0]
    assert "Split onto separate lines" in msgs[0]


def test_rule_e_count_correct_below_4backtick_wrapper() -> None:
    """Scenario 1 + Rule E: with the 4-backtick wrapper handled correctly,
    the max line-start enumeration item is 14 (not whatever appears before
    the wrapper). Pre-fix the slice was truncated and Rule E saw only items
    above the wrapper.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 5 extra) — runs\n\n"
        "9. local-only\n\n"
        "````markdown\n"
        "```python\n"
        "### inside python block\n"
        "```\n"
        "````\n\n"
        "10. real-gate\n"
        "11. real-gate\n"
        "12. real-gate\n"
        "13. real-gate\n"
        "14. real-gate\n"
        "\n- all 15 gates pass — required for merge.\n"
    )
    # Header claims 9+5=14 extras header_n=5 → max=14 → expected_extras=14-8=6, claim says 5 → drift
    # all_K=15 → expected_total = 14+1 = 15 → no drift on K.
    msgs = scan_ci_gate_claims(fixture)
    assert any("9 + 5 extra" in m for m in msgs), msgs
    assert any("reaches item 14" in m for m in msgs), msgs


def test_4backtick_wrapper_not_closed_by_3backticks() -> None:
    """Scenario 3: CommonMark says a 4-backtick fence is NOT closed by a
    bare 3-backtick line (close run must be ≥ open run). Pre-fix the toggle
    was length-blind so the 3-backtick line wrongly closed the wrapper,
    making subsequent content visible to the slice when it should be inside
    the still-open fence.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "````markdown\n"
        "### heading inside the wrapper\n"
        "```\n"
        "still inside the 4-backtick wrapper because 3 < 4\n"
        "### another heading still inside\n"
        "````\n\n"
        "10. truly-real-gate\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    # Post-fix: only the closing 4-backticks (or stronger) close the wrapper.
    # The interior `### heading inside the wrapper` and `### another heading
    # still inside` are content; they must NOT terminate the slice.
    assert "10. truly-real-gate" in body, (
        f"4-backtick wrapper must not be closed by 3-backticks; got: {body!r}"
    )
    assert "Real next section" not in body


def test_5backtick_wrapper_with_4backtick_inner() -> None:
    """Scenario 5: generalize beyond the 4/3 case. A 5-backtick wrapper
    containing a 4-backtick fence keeps the wrapper open. Pre-fix any
    triple-backtick prefix toggled, so the inner 4-backtick line wrongly
    closed the 5-backtick wrapper.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "`````markdown\n"
        "````nested\n"
        "### heading inside double-nested fence\n"
        "````\n"
        "still inside the 5-backtick wrapper\n"
        "`````\n\n"
        "10. real-gate-after-nested-fence\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. real-gate-after-nested-fence" in body, (
        f"5-backtick wrapper must not be closed by 4-backtick inner; got: {body!r}"
    )
    assert "Real next section" not in body


def test_close_fence_with_info_string_does_not_close() -> None:
    r"""Scenario 4: a ```python line cannot close an open fence — close
    fences MUST have empty info-string (whitespace-only after the run) per
    CommonMark §4.5. A heading inside such a fence must remain content.

    Pre-fix the walker toggled on any ```-prefixed line, so a
    ```python inside a 3-backtick fence wrongly closed it, exposing
    later headings to the slice-termination regex.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "```text\n"
        "Here is the canonical opener for a python fence:\n"
        "```python\n"
        "### heading-shaped line that must stay inside the still-open fence\n"
        "```\n\n"
        "10. real-gate-after-info-string-not-close\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    # Post-fix: ```python (info-string `python`) does NOT close the outer
    # 3-backtick fence — only a ``` line whose post-tick content is
    # whitespace-only is a valid close. So the inner `### heading…` is
    # still content. The empty ``` two lines later closes the fence.
    assert "10. real-gate-after-info-string-not-close" in body, (
        f"close-fence with info-string must not close; got: {body!r}"
    )
    assert "Real next section" not in body


def test_open3_close4_still_closes() -> None:
    """Scenario 6 (regression sentinel): open with 3 backticks, close with
    4 (≥3, info-string empty) — CommonMark says this closes. Verifies the
    ``ticks ≥ fence_len`` discriminator. Passes pre- AND post-fix because
    the old length-blind toggle accidentally treated the 4-tick line as a
    close (any backtick run was a toggle); the new walker reaches the same
    answer for the right reason.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 2 extra) — runs\n\n"
        "9. local-only\n\n"
        "```\n"
        "### heading inside 3-tick fence\n"
        "````\n\n"
        "10. real-gate-after-mismatched-close\n"
        "11. another\n"
        "\n## Real next section\n\n"
        "(other content)\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    assert "10. real-gate-after-mismatched-close" in body, (
        f"4-tick line must close 3-tick fence; got: {body!r}"
    )
    assert "11. another" in body
    assert "Real next section" not in body

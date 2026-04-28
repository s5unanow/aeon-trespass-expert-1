"""Tests for S5U-744 — tilde-fence asymmetry mechanical guards.

Two complementary mechanical guards:

1. **Asymmetry sentinel** — pins the current "tilde NOT honored"
   behavior of `_instruction_drift_rule_e.walk_with_fence_state`. If a
   future PR honors `~~~` without updating Rule F's caller and Rule G's
   corpus guard in lockstep, this test fails and forces an audit.
2. **Rule G corpus guard** — scans CLAUDE.md for active tilde fences and
   fires a drift message naming the line and the S5U-744 remediation
   paths. Converts the documented S5U-742/S5U-743 asymmetry into a
   fail-closed signal.

## Red-before evidence

The Rule G module (`scripts/_instruction_drift_rule_g.py`) does not exist
in pre-fix code. At commit f06b56b (current main HEAD pre-PR), running

    python -c "import sys; sys.path.insert(0, 'scripts'); \\
               import _instruction_drift_rule_g"

fails with `ModuleNotFoundError: No module named '_instruction_drift_rule_g'`.
Every Rule G test in this file imports that module at collection time and
would fail to collect at the cited SHA.

The asymmetry sentinel test is the carve-out form
(`Red-before confirmation: N/A — sentinel test pins existing invariant;
no production code change`): it asserts the *current* walker behavior with
no paired production-code change. The walker remains unchanged in this PR;
the sentinel exists to detect FUTURE changes that violate the lockstep
contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_instruction_drift.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _instruction_drift_rule_e import _ci_section_body  # noqa: E402
from _instruction_drift_rule_g import scan_claude_md_tilde_fences  # noqa: E402

# ---------------------------------------------------------------------------
# Asymmetry sentinel — pins `walk_with_fence_state` current behavior.
# ---------------------------------------------------------------------------


def test_ci_body_slice_does_not_honor_tilde_fence_documented_asymmetry() -> None:
    """Sentinel: tilde fences are intentionally NOT honored.

    If this test fails, you changed the fence detector — you MUST also:

    1. Update Rule F's caller (which reuses the shared
       `walk_with_fence_state` helper from
       `scripts/_instruction_drift_rule_e.py`) in the same PR, or confirm
       the shared walker covers Rule F automatically.
    2. Update the docstring on `walk_with_fence_state` in
       `scripts/_instruction_drift_rule_e.py` that documents this
       asymmetry.
    3. Drop or relax Rule G's corpus guard
       (`scripts/_instruction_drift_rule_g.py`) — active tilde fences
       become safe once the walker honors them, so the corpus ban can
       be removed.
    4. Remove this sentinel test.

    See S5U-744 for the rationale: the asymmetry is currently inert
    (CLAUDE.md uses no tilde fences) but a future edit introducing one
    re-opens the S5U-742 bypass class. This sentinel forces an audit
    when the walker behavior changes.
    """
    fixture = (
        "# CLAUDE.md\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n\n"
        "~~~markdown\n### inside tilde fence\n~~~\n\n"
        "10. should-be-cut-off\n"
        "\n## terminator\n"
    )
    body, _hl, _n = _ci_section_body(fixture)
    # Current behavior (asymmetry preserved): the in-fence `### ` is NOT
    # skipped because the walker does not track tilde fences. The slice
    # therefore terminates at the `### inside tilde fence` line, and
    # `10. should-be-cut-off` (which would be a real gate item below the
    # tilde fence) is invisible to Rule E's count derivation and Rule F's
    # mid-line scan.
    assert "10. should-be-cut-off" not in body, (
        "Sentinel violated: the body slice now extends past the tilde-"
        "fenced ### line. If you legitimately changed `walk_with_fence_state` "
        "to honor `~~~`, follow the four-step lockstep update in this test's "
        "docstring. See S5U-744."
    )
    # Symmetric assertion: the `### inside tilde fence` line itself
    # terminates the slice. (If the walker started honoring tildes, the
    # in-fence heading would be skipped and the slice would extend, so
    # this string would appear in `body`.)
    assert "inside tilde fence" not in body


# ---------------------------------------------------------------------------
# Rule G — CLAUDE.md tilde-fence corpus guard.
# ---------------------------------------------------------------------------


def test_rule_g_clean_input_returns_empty() -> None:
    """Happy-path: text with no `~~~` returns empty drift list."""
    text = (
        "# CLAUDE.md\n\n"
        "## Quality gates\n\n"
        "Some prose. No tilde fences.\n\n"
        "```python\nprint('hi')\n```\n\n"
        "More prose.\n"
    )
    assert scan_claude_md_tilde_fences(text) == []


def test_rule_g_real_claude_md_is_clean() -> None:
    """The real CLAUDE.md must currently contain no active tilde fences."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert scan_claude_md_tilde_fences(claude_md) == []


def test_rule_g_three_tilde_fence_fires() -> None:
    """Failure input: a 3-tilde fence at line start fires."""
    text = "# CLAUDE.md\n\n~~~markdown\n### inside\n~~~\nafter\n"
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, msgs  # opener + closer both flagged
    assert "tilde fence" in msgs[0]
    assert "S5U-744" in msgs[0]
    # Line numbers should reference the offending lines (1-indexed).
    assert "CLAUDE.md:3" in msgs[0]


def test_rule_g_four_tilde_fence_fires() -> None:
    """G2 alias: a 4-tilde fence (≥3 per CommonMark) also fires."""
    text = "# CLAUDE.md\n\n~~~~markdown\n### inside\n~~~~\n"
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, msgs
    assert all("tilde fence" in m for m in msgs)


def test_rule_g_indented_tilde_fence_fires() -> None:
    """G2 alias: a CommonMark-allowed indented (≤3 spaces) tilde fence fires."""
    text = "# CLAUDE.md\n\n   ~~~markdown\n   ### inside\n   ~~~\n"
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, msgs


def test_rule_g_over_indented_tilde_does_not_fire() -> None:
    """CommonMark §4.5: >3 leading spaces is NOT a fence (it's an indented
    code block). Rule G honors this — over-indented `~~~` is not flagged.
    """
    text = "# CLAUDE.md\n\n    ~~~markdown\n    not a fence\n    ~~~\n"
    assert scan_claude_md_tilde_fences(text) == []


def test_rule_g_two_tilde_does_not_fire() -> None:
    """A 2-tilde line is not a CommonMark fence (requires ≥3) — does not fire."""
    text = "# CLAUDE.md\n\n~~ not a fence ~~\n"
    assert scan_claude_md_tilde_fences(text) == []


def test_rule_g_mid_line_tilde_does_not_fire() -> None:
    """`~~~` in the middle of prose is not a CommonMark fence — does not fire."""
    text = "# CLAUDE.md\n\nThis prose mentions ~~~ as a sigil.\n"
    assert scan_claude_md_tilde_fences(text) == []


def test_rule_g_tilde_inside_backtick_fence_does_not_fire() -> None:
    """Adversarial nested case: a `~~~` line INSIDE a backtick code fence
    is content, not active markdown. Rule G uses the shared walker to
    skip backtick-fenced regions and must not false-positive on
    documentation that demonstrates tilde syntax.
    """
    text = (
        "# CLAUDE.md\n\n"
        "Documenting tilde fences:\n\n"
        "```markdown\n"
        "~~~markdown\n"
        "this is sample content showing what a tilde fence looks like\n"
        "~~~\n"
        "```\n"
    )
    assert scan_claude_md_tilde_fences(text) == []


def test_rule_g_tilde_after_backtick_fence_closes_fires() -> None:
    """Adversarial: a `~~~` line AFTER a closed backtick fence (i.e.,
    outside the fence) IS active markdown and must fire. Confirms the
    walker correctly closes the backtick fence.
    """
    text = (
        "# CLAUDE.md\n\n"
        "```markdown\nexample\n```\n\n"  # closed backtick fence
        "~~~markdown\nactive tilde fence\n~~~\n"  # outside, must fire
    )
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, msgs


def test_rule_g_empty_input_returns_empty() -> None:
    """G1: empty input returns []. The orchestrator's earlier read-failure
    path handles the missing-file case before Rule G runs.
    """
    assert scan_claude_md_tilde_fences("") == []


def test_rule_g_message_contains_remediation_paths() -> None:
    """The drift message must point at S5U-744's two remediation paths
    so a future contributor knows how to resolve it.
    """
    text = "# CLAUDE.md\n\n~~~markdown\n### inside\n~~~\n"
    msgs = scan_claude_md_tilde_fences(text)
    assert msgs
    msg = msgs[0]
    # (1) restructure to avoid the tilde fence
    assert "restructure" in msg.lower() or "convert" in msg.lower()
    # (2) extend the walker to honor tildes symmetrically
    assert "walk_with_fence_state" in msg or "honor" in msg
    # Cite the docstring location and the issue.
    assert "scripts/_instruction_drift_rule_e.py" in msg
    assert "S5U-744" in msg


# ---------------------------------------------------------------------------
# Integration — orchestrator wiring.
# ---------------------------------------------------------------------------


def test_orchestrator_clean_on_real_repo() -> None:
    """The real repo's CLAUDE.md is clean — orchestrator exits 0."""
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


def test_orchestrator_flags_synthetic_tilde_fence(tmp_path: Path) -> None:
    """A synthetic CLAUDE.md with an active tilde fence causes the
    orchestrator to exit 1 with a Rule G message naming S5U-744.

    The fixture is otherwise consistent (Rule E/F clean) so only Rule G
    fires.
    """
    review_md = tmp_path / ".claude" / "prompts" / "review.md"
    review_md.parent.mkdir(parents=True, exist_ok=True)
    review_md.write_text("1. **x**\n2. **y**\n", encoding="utf-8")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# CLAUDE.md\n\n"
        "Any safety-gate scope (hooks, review gates) should …\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs …\n\n"
        "9. local-only\n"
        "\n- all 10 gates pass — required for merge.\n\n"
        "## Some other section\n\n"
        "~~~markdown\n"
        "### inside\n"
        "~~~\n",
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
    assert "tilde fence" in combined
    assert "S5U-744" in combined


def test_rule_g_does_not_raise_on_arbitrary_text() -> None:
    """G1 robustness: pure-ascii, unicode, mixed line endings — no
    pathological text raises. The function is a pure walker.
    """
    samples = [
        "",
        "no fences\n",
        "single line, no newline",
        "unicode: ☃ snowman\n",
        "mixed line endings\r\nrow 2\r\nrow 3\n",
        "~~~",  # truncated final line, no newline
    ]
    for text in samples:
        # Should not raise.
        result = scan_claude_md_tilde_fences(text)
        assert isinstance(result, list)


def test_rule_g_isolation_from_rules_e_f(tmp_path: Path) -> None:
    """Rule G is independent of Rule E/F's body extraction — it scans
    the entire CLAUDE.md file, not just the CI section. A tilde fence
    OUTSIDE the CI section still fires.
    """
    text = (
        "# CLAUDE.md\n\n"
        "## Some unrelated section\n\n"
        "~~~markdown\nactive tilde fence in non-CI section\n~~~\n\n"
        "### CI (GitHub Actions, 9 + 1 extra) — runs\n\n"
        "9. local-only\n"
    )
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, msgs


@pytest.mark.parametrize(
    "fence_chars",
    ["~~~", "~~~~", "~~~~~", "~~~~~~~~~~"],
)
def test_rule_g_g2_tilde_run_lengths(fence_chars: str) -> None:
    """G2 content-derived: any ≥3-tilde run at line start is a fence
    (CommonMark §4.5). Parametrize over a handful of run lengths.
    """
    text = f"# CLAUDE.md\n\n{fence_chars}\ncontent\n{fence_chars}\n"
    msgs = scan_claude_md_tilde_fences(text)
    assert len(msgs) == 2, (fence_chars, msgs)

"""Integration tests for shell hooks with adversarial inputs.

Tests .claude/hooks/pre-pr-check.sh and .claude/hooks/pre-commit-check.sh
against synthetic inputs to validate safety gating logic.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PRE_PR_CHECK = REPO_ROOT / ".claude" / "hooks" / "pre-pr-check.sh"
PRE_COMMIT_CHECK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-check.sh"

# Canonical well-formed review body: every new gate (verdict, structured
# fields, probe count) passes. Tests can splice or omit pieces to target a
# specific gate.
CANONICAL_STRUCTURED_BODY = """\
## Review

1. [NIT] example.py:1 — stylistic nit.

## Verdict

Verdict: PASS
Critical: none
Warning: none
Suggestion: tighten wording
Probes run:
- ran `git diff main...HEAD` and read all 3 touched files in full
- ran `uv run pytest -x -q --timeout=60 -m "not slow"` — all green
- verified success criterion "X happens when Y" against the implementation
Bug IDs filed: none

**PASS**
"""


def _run_pre_pr_check(
    review_file: Path | None,
    *,
    head_time: int | None = None,
    staleness_enabled: bool = False,
) -> int:
    """Test pre-pr-check.sh verdict logic with a synthetic review artifact.

    Replicates the verdict-checking and S5U-613 structured-contract portions
    of pre-pr-check.sh in an isolated script so tests don't depend on git
    state or hardcoded paths. If the hook's logic changes, these tests must
    be updated to match.
    """
    env_input = '{"command": "gh pr create --title test"}'
    script = _build_pr_check_script(
        review_file,
        head_time=head_time,
        staleness_enabled=staleness_enabled,
    )
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"CLAUDE_TOOL_INPUT": env_input, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        timeout=5,
    )
    return result.returncode


def _build_pr_check_script(
    review_file: Path | None,
    *,
    head_time: int | None,
    staleness_enabled: bool,
) -> str:
    """Build a self-contained script replicating pre-pr-check.sh verdict logic.

    Mirrors the three gates the production hook applies after CLAUDE_TOOL_INPUT
    filtering: (1) original verdict presence/BLOCK check, (2) S5U-613 structured
    field + probe-count check, (3) S5U-613 staleness check.
    """
    review_path = str(review_file) if review_file else "/nonexistent/review.md"
    staleness_block = ""
    if staleness_enabled and head_time is not None:
        # Inline a hardcoded HEAD_TIME instead of calling git — tests control it.
        staleness_block = f"""
HEAD_TIME={head_time}
REVIEW_MTIME=$(stat -c %Y "$REVIEW_FILE" 2>/dev/null \\
  || stat -f %m "$REVIEW_FILE" 2>/dev/null \\
  || echo 0)
if [ "$HEAD_TIME" -gt 0 ] \\
  && [ "$REVIEW_MTIME" -gt 0 ] \\
  && [ "$REVIEW_MTIME" -lt "$HEAD_TIME" ]; then
  exit 1
fi
"""
    return f"""\
set -euo pipefail

REVIEW_FILE="{review_path}"

if [ ! -f "$REVIEW_FILE" ]; then
  exit 0
fi

# S5U-613: verdict is the last non-blank line (prevents backtick-quoted
# references to **BLOCK**/**PASS** inside findings from flipping the gate).
FINAL_LINE=$(grep -vE '^[[:space:]]*$' "$REVIEW_FILE" | tail -1)

if ! echo "$FINAL_LINE" | grep -qE '^\\*\\*(BLOCK|PASS WITH WARNINGS|PASS)\\*\\*[[:space:]]*$'; then
  exit 1
fi

if echo "$FINAL_LINE" | grep -qE '^\\*\\*BLOCK\\*\\*[[:space:]]*$'; then
  exit 1
fi

# S5U-613: structured verdict contract
if ! grep -qE '^Verdict:[[:space:]]+(PASS|PASS WITH WARNINGS|BLOCK)' "$REVIEW_FILE"; then
  exit 1
fi

if ! grep -qE '^Probes run:' "$REVIEW_FILE"; then
  exit 1
fi

PROBE_COUNT=$(awk '
  /^Probes run:/ {{ in_probes = 1; next }}
  in_probes && /^[A-Za-z].*:/ {{ in_probes = 0 }}
  in_probes && /^-[[:space:]]+[^[:space:]]/ {{ count++ }}
  END {{ print count + 0 }}
' "$REVIEW_FILE")

if [ "$PROBE_COUNT" -lt 3 ]; then
  exit 1
fi

# S5U-619: structured Verdict: field must agree with final-line token.
# Both locations are already validated above; extract the tokens and require
# byte-equality. Without this, `Verdict: BLOCK` + `**PASS**` would pass the
# gate because each check independently saw a valid verdict token.
FIELD_VERDICT=$(grep -E '^Verdict:[[:space:]]+(PASS|PASS WITH WARNINGS|BLOCK)' "$REVIEW_FILE" \\
  | head -1 \\
  | sed -E 's/^Verdict:[[:space:]]+//; s/[[:space:]]+$//')
FINAL_VERDICT=$(echo "$FINAL_LINE" | sed -E 's/^\\*\\*(.*)\\*\\*[[:space:]]*$/\\1/')
if [ "$FIELD_VERDICT" != "$FINAL_VERDICT" ]; then
  exit 1
fi
{staleness_block}
exit 0
"""


class TestPrePrCheckVerdicts:
    """Test pre-pr-check.sh verdict detection with synthetic review files."""

    def test_pass_only(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY)
        assert _run_pre_pr_check(review) == 0

    def test_block_only(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY.replace("PASS", "BLOCK"))
        assert _run_pre_pr_check(review) != 0

    def test_pass_header_block_verdict(self, tmp_path: Path) -> None:
        """PASS in section header + BLOCK as final verdict should block."""
        review = tmp_path / "review.md"
        review.write_text(
            "## Section: **PASS** on formatting\n\n"
            "## Verdict\n\n"
            "Verdict: BLOCK\n"
            "Probes run:\n- a\n- b\n- c\n\n"
            "**BLOCK**\n"
        )
        assert _run_pre_pr_check(review) != 0

    def test_block_in_body_pass_final_line_passes(self, tmp_path: Path) -> None:
        """S5U-613 scenario D: backtick-quoted **BLOCK** in findings must not flip the gate.

        The old hook blocked on any `**BLOCK**` substring, which meant a
        reviewer mentioning the word inside a quoted reference (e.g., when
        explaining a regex in the audit trail) would self-sabotage their own
        PASS review. The new hook anchors verdict detection to the final
        non-blank line.
        """
        review = tmp_path / "review.md"
        review.write_text(
            "## Findings\n\n"
            "- traced regex behavior: `**BLOCK**` in body no longer flips the gate\n\n"
            "## Verdict\n\n"
            "Verdict: PASS\n"
            "Probes run:\n- a\n- b\n- c\n\n"
            "**PASS**\n"
        )
        assert _run_pre_pr_check(review) == 0

    def test_trailing_whitespace_final_line_still_recognised(self, tmp_path: Path) -> None:
        """Trailing spaces on the verdict line must not break detection."""
        review = tmp_path / "review.md"
        review.write_text(
            "## Verdict\n\nVerdict: PASS\nProbes run:\n- a\n- b\n- c\n\n**PASS**   \n"
        )
        assert _run_pre_pr_check(review) == 0

    def test_verdict_not_on_final_line_blocks(self, tmp_path: Path) -> None:
        """If the verdict is not the last non-blank line, the gate blocks.

        This guards against trailing commentary appended after the verdict.
        """
        review = tmp_path / "review.md"
        review.write_text(
            "## Verdict\n\n"
            "Verdict: PASS\n"
            "Probes run:\n- a\n- b\n- c\n\n"
            "**PASS**\n\n"
            "trailing afterthought that invalidates placement\n"
        )
        assert _run_pre_pr_check(review) != 0

    def test_empty_file(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text("")
        # No verdict found → exits non-zero (no verdict = blocked)
        assert _run_pre_pr_check(review) != 0

    def test_missing_file(self) -> None:
        assert _run_pre_pr_check(None) == 0

    def test_pass_with_warnings(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY.replace("PASS", "PASS WITH WARNINGS"))
        assert _run_pre_pr_check(review) == 0


class TestPrePrCheckStructuredContract:
    """S5U-613: enforce structured verdict fields and probe-count floor.

    The original hook accepted any file containing `**PASS**`. A worker could
    fabricate a two-line artifact to pass the gate. These tests pin the
    structured-field contract that blocks that bypass.
    """

    def test_bare_verdict_no_structure_blocks(self, tmp_path: Path) -> None:
        """A minimal artifact with just `**PASS**` must be rejected.

        This is the exact attack in plan-s5u-613.md scenario B.
        """
        review = tmp_path / "review.md"
        review.write_text("**PASS**\n")
        assert _run_pre_pr_check(review) != 0

    def test_missing_structured_verdict_field_blocks(self, tmp_path: Path) -> None:
        """Artifact has `**PASS**` and probes, but no `Verdict:` line."""
        review = tmp_path / "review.md"
        body = CANONICAL_STRUCTURED_BODY.replace("Verdict: PASS\n", "")
        review.write_text(body)
        assert _run_pre_pr_check(review) != 0

    def test_missing_probes_run_field_blocks(self, tmp_path: Path) -> None:
        """Artifact has `Verdict:` but no `Probes run:` audit trail."""
        review = tmp_path / "review.md"
        # Remove the entire probes block (Probes run: header + its 3 bullets)
        lines = CANONICAL_STRUCTURED_BODY.splitlines(keepends=True)
        filtered = []
        skip = False
        for ln in lines:
            if ln.startswith("Probes run:"):
                skip = True
                continue
            if skip and ln.startswith("-"):
                continue
            if skip and not ln.startswith("-"):
                skip = False
            filtered.append(ln)
        review.write_text("".join(filtered))
        assert _run_pre_pr_check(review) != 0

    def test_too_few_probe_bullets_blocks(self, tmp_path: Path) -> None:
        """Fewer than 3 probe bullets signals a perfunctory review."""
        review = tmp_path / "review.md"
        body = CANONICAL_STRUCTURED_BODY
        # Replace the 3-probe block with a 1-probe block
        body = body.replace(
            "Probes run:\n"
            "- ran `git diff main...HEAD` and read all 3 touched files in full\n"
            '- ran `uv run pytest -x -q --timeout=60 -m "not slow"` — all green\n'
            '- verified success criterion "X happens when Y" against the implementation\n',
            "Probes run:\n- ran git diff\n",
        )
        review.write_text(body)
        assert _run_pre_pr_check(review) != 0

    def test_exactly_three_probes_passes(self, tmp_path: Path) -> None:
        """Three probes is the minimum that satisfies the audit-trail floor."""
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY)
        assert _run_pre_pr_check(review) == 0

    def test_structured_verdict_disagrees_with_final_line_blocks(self, tmp_path: Path) -> None:
        """S5U-619: `Verdict: BLOCK` + `**PASS**` final line must block.

        The hook reads two verdict locations but historically did not require
        them to agree. A review artifact stating `Verdict: BLOCK` in the
        structured field with `**PASS**` as its final non-blank line would pass
        the gate — either a copy-paste error silently flipping a BLOCK to a
        PASS, or a deliberate bypass that looks innocent in the artifact.
        """
        review = tmp_path / "review.md"
        review.write_text(
            "## Verdict\n\n"
            "Verdict: BLOCK\n"
            "Critical:\n- genuine critical issue\n"
            "Probes run:\n- a\n- b\n- c\n\n"
            "**PASS**\n"
        )
        assert _run_pre_pr_check(review) != 0

    def test_structured_verdict_pass_with_warnings_vs_pass_blocks(self, tmp_path: Path) -> None:
        """S5U-619 adversarial: `Verdict: PASS WITH WARNINGS` + `**PASS**` blocks.

        A typo across the two verdict locations — the structured field and the
        final-line token must be byte-equal tokens, not merely non-BLOCK.
        """
        review = tmp_path / "review.md"
        review.write_text(
            "## Verdict\n\nVerdict: PASS WITH WARNINGS\nProbes run:\n- a\n- b\n- c\n\n**PASS**\n"
        )
        assert _run_pre_pr_check(review) != 0

    def test_structured_verdict_agreement_passes(self, tmp_path: Path) -> None:
        """S5U-619 happy-path: agreeing tokens still pass.

        Guards against the equality check over-rejecting well-formed artifacts.
        """
        review = tmp_path / "review.md"
        review.write_text(
            "## Verdict\n\n"
            "Verdict: PASS WITH WARNINGS\n"
            "Probes run:\n- a\n- b\n- c\n\n"
            "**PASS WITH WARNINGS**\n"
        )
        assert _run_pre_pr_check(review) == 0

    def test_probe_bullets_after_next_section_do_not_count(self, tmp_path: Path) -> None:
        """Bullets after `Probes run:` but under a following header must not count.

        Guards against an artifact with only 1 real probe bullet, padded with
        bullets from a later field list.
        """
        review = tmp_path / "review.md"
        body = (
            "## Verdict\n\n"
            "Verdict: PASS\n"
            "Critical: none\n"
            "Warning: none\n"
            "Probes run:\n"
            "- only one real probe\n"
            "Bug IDs filed:\n"
            "- fake-bullet-a\n"
            "- fake-bullet-b\n"
            "\n**PASS**\n"
        )
        review.write_text(body)
        assert _run_pre_pr_check(review) != 0


class TestPrePrCheckStaleness:
    """S5U-613: artifacts older than HEAD are rejected (plan scenario C)."""

    def test_fresh_artifact_passes(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY)
        mtime = review.stat().st_mtime
        # HEAD commit is 60s earlier than the review → review is fresh.
        head_time = int(mtime) - 60
        assert _run_pre_pr_check(review, head_time=head_time, staleness_enabled=True) == 0

    def test_stale_artifact_blocks(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY)
        mtime = review.stat().st_mtime
        # HEAD commit is 60s *later* than the review → review is stale.
        head_time = int(mtime) + 60
        assert _run_pre_pr_check(review, head_time=head_time, staleness_enabled=True) != 0

    def test_artifact_equal_to_head_passes(self, tmp_path: Path) -> None:
        """Artifact mtime == HEAD commit time is not stale (boundary case)."""
        review = tmp_path / "review.md"
        review.write_text(CANONICAL_STRUCTURED_BODY)
        # Force mtime to match head_time exactly.
        head_time = int(review.stat().st_mtime)
        os.utime(review, (head_time, head_time))
        assert _run_pre_pr_check(review, head_time=head_time, staleness_enabled=True) == 0


class TestPreCommitCheckToolchain:
    """Validate pre-commit-check.sh uses correct toolchain wrappers."""

    def test_all_python_gates_use_uv_run(self) -> None:
        content = PRE_COMMIT_CHECK.read_text()
        # Find all run_gate lines with Python tools
        python_tools = ["ruff", "mypy", "lint-imports", "pytest"]
        for tool in python_tools:
            lines = [ln for ln in content.splitlines() if "run_gate" in ln and tool in ln]
            for line in lines:
                assert "uv run" in line, f"Gate for '{tool}' must use 'uv run': {line}"

    def test_all_js_gates_use_pnpm(self) -> None:
        content = PRE_COMMIT_CHECK.read_text()
        js_tools = ["oxlint", "tsc"]
        for tool in js_tools:
            lines = [ln for ln in content.splitlines() if "run_gate" in ln and tool in ln]
            for line in lines:
                assert "pnpm" in line, f"Gate for '{tool}' must use 'pnpm': {line}"

    def test_no_bare_tool_invocations(self) -> None:
        """Ensure no run_gate calls use bare tool names without wrappers."""
        content = PRE_COMMIT_CHECK.read_text()
        bare_tools = [
            " ruff check",
            " ruff format",
            " mypy ",
            " pytest ",
            " oxlint",
            " tsc",
        ]
        for line in content.splitlines():
            if "run_gate" not in line:
                continue
            for bare in bare_tools:
                if bare in line:
                    # Must be prefixed by 'uv run' or 'pnpm'
                    assert "uv run" in line or "pnpm" in line, (
                        f"Bare tool invocation found: {line.strip()}"
                    )

    def test_gates_exit_on_failure(self) -> None:
        """Each gate must have || exit 1 for fail-fast behavior."""
        content = PRE_COMMIT_CHECK.read_text()
        gate_lines = [ln for ln in content.splitlines() if ln.strip().startswith("run_gate ")]
        assert len(gate_lines) == 8, f"Expected 8 gates, found {len(gate_lines)}"
        for line in gate_lines:
            assert "|| exit 1" in line, f"Gate missing fail-fast: {line.strip()}"

    def test_script_has_set_euo_pipefail(self) -> None:
        content = PRE_COMMIT_CHECK.read_text()
        assert "set -euo pipefail" in content

"""Integration tests for shell hooks with adversarial inputs.

Tests .claude/hooks/pre-pr-check.sh and .claude/hooks/pre-commit-check.sh
against synthetic inputs to validate safety gating logic.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PRE_PR_CHECK = REPO_ROOT / ".claude" / "hooks" / "pre-pr-check.sh"
PRE_COMMIT_CHECK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-check.sh"


def _run_pre_pr_check(review_file: Path | None) -> int:
    """Test pre-pr-check.sh verdict logic with a synthetic review artifact.

    Replicates the verdict-checking portion of pre-pr-check.sh (lines 34-47)
    in an isolated script so tests don't depend on git state or hardcoded paths.
    If the hook's verdict logic changes, these tests must be updated to match.
    """
    env_input = '{"command": "gh pr create --title test"}'
    script = _build_pr_check_script(review_file)
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"CLAUDE_TOOL_INPUT": env_input, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        timeout=5,
    )
    return result.returncode


def _build_pr_check_script(review_file: Path | None) -> str:
    """Build a self-contained script replicating pre-pr-check.sh verdict logic."""
    review_path = str(review_file) if review_file else "/nonexistent/review.md"
    return f"""\
set -euo pipefail

# Simulate CLAUDE_TOOL_INPUT check (already filtered by caller)
REVIEW_FILE="{review_path}"

if [ ! -f "$REVIEW_FILE" ]; then
  exit 0
fi

if ! grep -qE '\\*\\*(BLOCK|PASS WITH WARNINGS|PASS)\\*\\*' "$REVIEW_FILE"; then
  exit 1
fi

if grep -qE '\\*\\*BLOCK\\*\\*' "$REVIEW_FILE" && ! grep -qE '\\*\\*PASS' "$REVIEW_FILE"; then
  exit 1
fi

exit 0
"""


class TestPrePrCheckVerdicts:
    """Test pre-pr-check.sh verdict detection with synthetic review files."""

    def test_pass_only(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text("## Review\n\nVerdict: **PASS**\n")
        assert _run_pre_pr_check(review) == 0

    def test_block_only(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text("## Review\n\nVerdict: **BLOCK**\n")
        assert _run_pre_pr_check(review) != 0

    @pytest.mark.xfail(
        reason="S5U-414: BLOCK bypassed when PASS also present (line 42 logic bug)",
        strict=True,
    )
    def test_pass_header_block_verdict(self, tmp_path: Path) -> None:
        """PASS in section header + BLOCK as final verdict should block."""
        review = tmp_path / "review.md"
        review.write_text("## Section: **PASS** on formatting\n\n### Final Verdict\n\n**BLOCK**\n")
        assert _run_pre_pr_check(review) != 0

    def test_block_header_pass_verdict(self, tmp_path: Path) -> None:
        """BLOCK in section header + PASS as final verdict should allow."""
        review = tmp_path / "review.md"
        review.write_text(
            "## Section: **BLOCK** on linting (resolved)\n\n### Final Verdict\n\n**PASS**\n"
        )
        assert _run_pre_pr_check(review) == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text("")
        # No verdict found → exits non-zero (no verdict = blocked)
        assert _run_pre_pr_check(review) != 0

    def test_missing_file(self) -> None:
        assert _run_pre_pr_check(None) == 0

    def test_pass_with_warnings(self, tmp_path: Path) -> None:
        review = tmp_path / "review.md"
        review.write_text("## Review\n\nVerdict: **PASS WITH WARNINGS**\n")
        assert _run_pre_pr_check(review) == 0


class TestPreCommitCheckToolchain:
    """Validate pre-commit-check.sh uses correct toolchain wrappers."""

    def test_all_python_gates_use_uv_run(self) -> None:
        content = PRE_COMMIT_CHECK.read_text()
        # Find all run_gate lines with Python tools
        python_tools = ["ruff", "mypy", "lint-imports", "pytest"]
        for tool in python_tools:
            lines = [ln for ln in content.splitlines() if f"run_gate" in ln and tool in ln]
            for line in lines:
                assert "uv run" in line, f"Gate for '{tool}' must use 'uv run': {line}"

    def test_all_js_gates_use_pnpm(self) -> None:
        content = PRE_COMMIT_CHECK.read_text()
        js_tools = ["eslint", "tsc"]
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
            " eslint",
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

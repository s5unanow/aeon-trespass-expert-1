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


class TestPreCommitCheckFailOpenStructural:
    """S5U-1222: structural guards against the three fail-open vectors.

    1. The `--amend` early-exit must sit AFTER Gate 0 (secret scan), so an
       amend that stages a fresh secret is still scanned.
    2. No hardcoded `/Users/` path — the hook must resolve the repo root from
       the harness env / git, so worktrees and second clones validate the
       tree being committed.
    3. The trigger must not be the literal substring match `grep -q 'git
       commit'`, which is defeated by any flag between `git` and `commit`.
    """

    def test_no_hardcoded_users_path(self) -> None:
        """No absolute /Users/ path may remain (vector 2)."""
        content = PRE_COMMIT_CHECK.read_text()
        assert "/Users/" not in content, (
            "Hardcoded /Users/ path found; hook must resolve repo root from "
            "CLAUDE_PROJECT_DIR / git rev-parse --show-toplevel."
        )

    def test_cd_resolves_repo_root_dynamically(self) -> None:
        """The cd target must derive from CLAUDE_PROJECT_DIR or git, not a literal."""
        content = PRE_COMMIT_CHECK.read_text()
        assert "CLAUDE_PROJECT_DIR" in content, (
            "Hook must honor CLAUDE_PROJECT_DIR for the repo-root cd."
        )
        assert "git rev-parse --show-toplevel" in content, (
            "Hook must fall back to git rev-parse --show-toplevel when CLAUDE_PROJECT_DIR is unset."
        )

    def test_trigger_not_literal_substring(self) -> None:
        """The trigger must not be the flag-fragile literal `grep -q 'git commit'` (vector 3).

        Comment lines (which legitimately quote the retired pattern to explain
        the fix) are excluded; only an active code line using the literal
        substring match is a violation.
        """
        code_lines = [
            ln
            for ln in PRE_COMMIT_CHECK.read_text().splitlines()
            if not ln.lstrip().startswith("#")
        ]
        offenders = [ln for ln in code_lines if "grep -q 'git commit'" in ln]
        assert not offenders, (
            "Literal substring trigger is defeated by `git -C <p> commit`, "
            f"`git --no-pager commit`, etc. Use a flag-tolerant detector. "
            f"Offending line(s): {offenders}"
        )

    def test_amend_skip_appears_after_gate_0(self) -> None:
        """The `--amend` quality-gate skip must be positioned after Gate 0 (vector 1).

        Mirrors the plan's machine-checkable done criterion
        `awk '/--amend/{a=NR} /Gate 0/{g=NR} END{exit !(a>g)}'`.
        """
        lines = PRE_COMMIT_CHECK.read_text().splitlines()
        gate0_line = next(
            (i for i, ln in enumerate(lines) if "Gate 0" in ln),
            None,
        )
        amend_skip_line = next(
            (i for i, ln in enumerate(lines) if "--amend" in ln and "grep" in ln),
            None,
        )
        assert gate0_line is not None, "Could not locate the 'Gate 0' marker comment."
        assert amend_skip_line is not None, "Could not locate the `--amend` grep guard."
        assert amend_skip_line > gate0_line, (
            f"--amend skip (line {amend_skip_line + 1}) must come AFTER the "
            f"Gate 0 secret scan (line {gate0_line + 1}); otherwise an amend "
            f"bypasses the secret guard."
        )


def _run_pre_commit_hook(
    repo: Path,
    command: str,
    *,
    project_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the real pre-commit hook against a temp git repo.

    The hook reads CLAUDE_TOOL_INPUT (JSON) and cd's into CLAUDE_PROJECT_DIR.
    Pointing CLAUDE_PROJECT_DIR at the temp repo lets us exercise the trigger,
    branch guards, and Gate 0 hermetically — gates 1-8 are never reached in
    these scenarios because either Gate 0 exits first (secret staged) or the
    amend-skip exits right after Gate 0 (clean amend).
    """
    env = {
        "CLAUDE_TOOL_INPUT": f'{{"command": {command!r}}}'.replace("'", '"'),
        "CLAUDE_PROJECT_DIR": str(project_dir or repo),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(repo)),
    }
    return subprocess.run(
        ["bash", str(PRE_COMMIT_CHECK)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _init_feature_repo(repo: Path) -> None:
    """Init a git repo on a valid feature branch with one base commit."""
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    runners = dict(cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"], **runners)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "tester"], **runners)
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "s5unanow/s5u-1222-temp"],
        **runners,
    )
    base = repo / "base.txt"
    base.write_text("base\n")
    subprocess.run(["git", "-C", str(repo), "add", "base.txt"], **runners)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        **runners,
    )


class TestPreCommitCheckAmendSecretScan:
    """S5U-1222 vector 1 (behavioral): amend must not bypass Gate 0."""

    def test_amend_staging_secret_is_blocked(self, tmp_path: Path) -> None:
        """`git commit --amend` staging a fresh .env → BLOCKED by Gate 0 (S1)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        # Stage a fresh .env with an sk- key — both filename and content trip Gate 0.
        (repo / ".env").write_text("API_KEY=sk-abcdefgh12345678901234\n")
        subprocess.run(["git", "-C", str(repo), "add", ".env"], check=True, capture_output=True)
        result = _run_pre_commit_hook(repo, "git commit --amend --no-edit")
        assert result.returncode != 0, (
            "amend staging a secret must be BLOCKED by Gate 0; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "BLOCKED" in result.stdout, result.stdout

    def test_amend_without_secrets_skips_quality_gates(self, tmp_path: Path) -> None:
        """`git commit --amend` with no staged secrets → Gate 0 passes, gates 1-8 skipped (S2)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        (repo / "benign.txt").write_text("hello\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "benign.txt"],
            check=True,
            capture_output=True,
        )
        result = _run_pre_commit_hook(repo, "git commit --amend --no-edit")
        assert result.returncode == 0, (
            f"clean amend must pass; stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        # Skip message must mention the secret scan ran (accurate skip message).
        assert "secret scan" in result.stdout.lower(), (
            f"clean-amend skip message must state the secret scan ran: {result.stdout!r}"
        )


class TestPreCommitCheckTrigger:
    """S5U-1222 vector 3 (behavioral): flag-tolerant trigger.

    Each adversarial form must trigger the hook (reach the branch guards),
    which here means it cd's into the temp repo and runs Guard 1/2 + Gate 0.
    We assert the hook does NOT silently exit 0 as a no-op (it must reach the
    gate machinery). A non-commit command must be a clean no-op exit 0.
    """

    def test_git_dash_c_path_commit_triggers(self, tmp_path: Path) -> None:
        """`git -C <path> commit` must trigger (S3) — staged secret proves Gate 0 ran."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        (repo / ".env").write_text("API_KEY=sk-abcdefgh12345678901234\n")
        subprocess.run(["git", "-C", str(repo), "add", ".env"], check=True, capture_output=True)
        result = _run_pre_commit_hook(repo, "git -C /some/path commit -m x")
        assert result.returncode != 0 and "BLOCKED" in result.stdout, (
            f"`git -C ... commit` must reach Gate 0; stdout={result.stdout!r}"
        )

    def test_git_no_pager_commit_triggers(self, tmp_path: Path) -> None:
        """`git --no-pager commit` must trigger (S4)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        (repo / ".env").write_text("API_KEY=sk-abcdefgh12345678901234\n")
        subprocess.run(["git", "-C", str(repo), "add", ".env"], check=True, capture_output=True)
        result = _run_pre_commit_hook(repo, "git --no-pager commit -m x")
        assert result.returncode != 0 and "BLOCKED" in result.stdout, (
            f"`git --no-pager commit` must reach Gate 0; stdout={result.stdout!r}"
        )

    def test_git_dash_c_config_commit_triggers(self, tmp_path: Path) -> None:
        """`git -c k=v commit` (incl. core.hooksPath) must trigger (S4)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        (repo / ".env").write_text("API_KEY=sk-abcdefgh12345678901234\n")
        subprocess.run(["git", "-C", str(repo), "add", ".env"], check=True, capture_output=True)
        result = _run_pre_commit_hook(repo, "git -c core.hooksPath=/dev/null commit -m x")
        assert result.returncode != 0 and "BLOCKED" in result.stdout, (
            f"`git -c k=v commit` must reach Gate 0; stdout={result.stdout!r}"
        )

    def test_non_commit_command_is_noop(self, tmp_path: Path) -> None:
        """A command that does not run git commit must be a clean no-op (exit 0)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        # Even with a staged secret, `git status` must NOT trigger the scan.
        (repo / ".env").write_text("API_KEY=sk-abcdefgh12345678901234\n")
        subprocess.run(["git", "-C", str(repo), "add", ".env"], check=True, capture_output=True)
        result = _run_pre_commit_hook(repo, "git status")
        assert result.returncode == 0, (
            f"non-commit command must be a no-op exit 0; stdout={result.stdout!r}"
        )
        assert "BLOCKED" not in result.stdout

    def test_empty_tool_input_is_clean_noop(self, tmp_path: Path) -> None:
        """Empty CLAUDE_TOOL_INPUT must exit 0 cleanly under set -euo pipefail (S7, G1)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_feature_repo(repo)
        result = subprocess.run(
            ["bash", str(PRE_COMMIT_CHECK)],
            capture_output=True,
            text=True,
            env={
                "CLAUDE_TOOL_INPUT": "",
                "CLAUDE_PROJECT_DIR": str(repo),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
            timeout=10,
        )
        assert result.returncode == 0, (
            f"empty CLAUDE_TOOL_INPUT must exit 0; stderr={result.stderr!r}"
        )

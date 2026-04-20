"""Tests for S5U-667 (Rule A structural match) + S5U-668 (Rule D advisory).

S5U-667 — the original S5U-658 `_SUBRANGE_CONTEXT_TOKENS` exemption was an
unbounded substring match, allowing any prose containing `trigger`,
`conditional`, or `always run` to silently exempt a stale check-count claim on
the same line. These tests pin the fix: the exemption must be *structural* —
only lines matching `^[\\s]*(bullet)? *Checks? \\d+[-–]\\d+ (and \\d+)?
(are|always) (run|conditional)` are exempt.

S5U-668 — the scanner docstring advertised a Rule D (required-check advisory)
that was never implemented. Coordinator picked option 1 (implement as
warning-only) because the drift class has bitten the repo across
S5U-638 / S5U-653 / S5U-654. These tests pin the behavior:
- Happy-path (aligned) → silent, exit 0
- Failure (drift) → advisory printed to stdout, exit 0 (warning-only)
- Malformed YAML → stderr warning, scanner continues, exit 0
- Missing workflows dir → no crash, exit 0

Red-before: tests committed first on branch
`s5unanow/s5u-667-s5u-668-drift-scanner-fixes` before the scanner fix landed.
See the commit message on the test-introduction commit for the exact SHA and
captured pre-fix failure excerpt.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_instruction_drift.py"


@pytest.fixture()
def scanner(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import scripts/check_instruction_drift.py as a module."""
    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parent))
    spec = importlib.util.spec_from_file_location("check_instruction_drift", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_instruction_drift"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_instruction_drift", None)


def _write(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body))
    return p


def _seed_repo(tmp: Path, *, checks: int = 22) -> None:
    """Seed a minimal fake repo with review.md + CLAUDE.md so fail-closed
    derivation succeeds. Copy of the fixture from test_check_instruction_drift.py
    to keep these tests self-contained."""
    review = ["## What to check", ""]
    for i in range(1, checks + 1):
        review.append(f"{i}. **Check number {i}** — description.")
    _write(
        tmp / ".claude" / "prompts" / "review.md",
        "\n".join(review) + "\n",
    )
    _write(
        tmp / "CLAUDE.md",
        textwrap.dedent(
            """\
            **Safety-gate scope escalation (MUST):** any PR touching
            safety-gate scope (hooks, pre-commit checks, review gates, CI
            checks, merge guards, branch-protection-adjacent scripts,
            `.claude/skills/**/SKILL.md` edits) MUST additionally be shipped
            via `/coordinator`.
            """
        ),
    )


# -- S5U-667: Rule A structural sub-range exemption -----------------------


class TestS5U667StructuralSubrange:
    """The sub-range exemption must be structural, not an unbounded substring match."""

    def test_unbounded_trigger_substring_no_longer_exempt(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bare 'trigger' word in prose must NOT exempt a stale claim."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "When the review prompt gets a new trigger, walk checks 1-21 and "
            "note any mismatch.\n",
        )
        assert scanner.run(tmp_path) == 1
        assert "says 21, authoritative count is 22" in capsys.readouterr().err

    def test_unbounded_conditional_substring_no_longer_exempt(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bare 'conditional' word in prose must NOT exempt a stale claim."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "conditional release — walk checks 1-21 anyway.\n",
        )
        assert scanner.run(tmp_path) == 1
        assert "says 21, authoritative count is 22" in capsys.readouterr().err

    def test_unbounded_always_run_substring_no_longer_exempt(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bare 'always run' in prose must NOT exempt a stale claim."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "The tests always run checks 1-10 before anything else.\n",
        )
        assert scanner.run(tmp_path) == 1
        assert "says 10, authoritative count is 22" in capsys.readouterr().err

    def test_claude_md_line_145_regression_is_caught(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Regression pin for CLAUDE.md:145. The real line contains 'Triggers' as
        prose; pre-S5U-667 the 'trigger' substring exempted the whole line.
        Simulate a regression where the count drifts to 1-21 and confirm the
        scanner catches it."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "CLAUDE_EXCERPT.md",
            "4. Walk `.claude/prompts/review.md` check-by-check (checks 1-21) "
            "and apply each one honestly to the diff. Triggers (label-based, "
            "content-based) are the same; the difference is that you are the reviewer.\n",
        )
        assert scanner.run(tmp_path) == 1
        assert "says 21, authoritative count is 22" in capsys.readouterr().err

    def test_structural_subrange_with_bullet_marker_still_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        """Legitimate structural sub-range with leading bullet marker remains exempt."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "- Checks 1-13 always run.\n* Checks 14-21 are conditional.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_structural_subrange_with_indent_still_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        """Legitimate nested-indent structural sub-range remains exempt."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "    * Checks 1-13 always run.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_structural_subrange_with_en_dash_still_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        """En-dash structural sub-range remains exempt."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "Checks 1\u201313 always run. Checks 14\u201321 are conditional.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_structural_singular_check_prefix_still_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        """Singular 'Check N-M' structural form remains exempt."""
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "Check 1-13 always run.\n",
        )
        assert scanner.run(tmp_path) == 0


# -- S5U-668: Rule D required-check advisory ------------------------------


class TestS5U668RuleDAdvisory:
    """Rule D: warning-only advisory comparing workflow jobs against
    CLAUDE.md § Quality gates enumeration. Never changes exit code."""

    def _seed(self, tmp_path: Path) -> None:
        """Seed review.md + CLAUDE.md with a Quality gates section referencing
        a specific set of workflow jobs."""
        _write(
            tmp_path / ".claude" / "prompts" / "review.md",
            "## What to check\n\n"
            + "\n".join(f"{i}. **Check {i}** — x." for i in range(1, 23))
            + "\n",
        )
        _write(
            tmp_path / "CLAUDE.md",
            textwrap.dedent(
                """\
                safety-gate scope (hooks, pre-commit checks, review gates, CI
                checks, merge guards, branch-protection-adjacent scripts,
                `.claude/skills/**/SKILL.md` edits) canonical.

                ## Quality gates

                ### CI (GitHub Actions)

                13. `visual-regression / visual` — Playwright snapshots.
                14. `visual-gate-scope / scan` — scans YAML for forbidden flags.
                15. `coverage-table-scan / scan` — reads PR body.
                16. `check_instruction_drift.py` — this scanner.
                """
            ),
        )

    def test_happy_aligned_jobs_no_advisory(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All workflow jobs appear in CLAUDE.md § Quality gates → no advisory."""
        self._seed(tmp_path)
        _write(
            tmp_path / ".github" / "workflows" / "visual-regression.yml",
            "name: visual-regression\n"
            "on:\n  push: {}\n"
            "jobs:\n"
            "  visual:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n",
        )
        _write(
            tmp_path / ".github" / "workflows" / "visual-gate-scope.yml",
            "name: visual-gate-scope\n"
            "on:\n  push: {}\n"
            "jobs:\n"
            "  scan:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n",
        )
        assert scanner.run(tmp_path) == 0
        out = capsys.readouterr()
        # Advisory must NOT flag these well-known jobs as unknown.
        assert "visual-regression / visual" not in out.out or "not mentioned" not in out.out
        assert "visual-gate-scope / scan" not in out.out or "not mentioned" not in out.out

    def test_failure_extra_job_prints_advisory(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Extra workflow job not in CLAUDE.md → advisory printed; exit still 0."""
        self._seed(tmp_path)
        _write(
            tmp_path / ".github" / "workflows" / "unknown.yml",
            "name: unknown\n"
            "on:\n  push: {}\n"
            "jobs:\n"
            "  mysterious-job:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n",
        )
        exit_code = scanner.run(tmp_path)
        captured = capsys.readouterr()
        assert exit_code == 0  # warning-only
        # Advisory surfaces the extra job or workflow name.
        assert "mysterious-job" in captured.out or "unknown" in captured.out

    def test_adversarial_malformed_yaml_does_not_crash(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Malformed workflow YAML → warning surfaces; scanner continues; exit 0."""
        self._seed(tmp_path)
        _write(
            tmp_path / ".github" / "workflows" / "broken.yml",
            "name: broken\n:::not valid yaml:::\n\tjobs:\n  foo: [unclosed\n",
        )
        exit_code = scanner.run(tmp_path)
        captured = capsys.readouterr()
        # Scanner must not crash; Rule D is advisory-only so exit = 0.
        assert exit_code == 0
        # Some diagnostic naming the broken file must surface.
        combined = captured.err + captured.out
        assert "broken.yml" in combined or "Rule D" in combined

    def test_missing_workflows_dir_does_not_crash(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        """No .github/workflows/ → scanner continues; exit code only from A/B/C."""
        self._seed(tmp_path)
        assert scanner.run(tmp_path) == 0

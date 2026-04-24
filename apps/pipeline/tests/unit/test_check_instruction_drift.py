"""Tests for scripts/check_instruction_drift.py (S5U-658).

Three-input discipline per rule class: happy / failure / adversarial.
Red-before: before commit 00c9bff on branch s5unanow/s5u-658-instruction-drift-scanner
the scanner did not exist — every import below fails with ModuleNotFoundError.
Each test documents a rule the live scanner must enforce.
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
    """Seed a minimal fake repo with review.md + CLAUDE.md so the scanner's
    fail-closed derivation succeeds. Includes a minimal CI section so
    Rule E (S5U-694) can parse the CI gate count."""
    review = ["## What to check", ""]
    for i in range(1, checks + 1):
        review.append(f"{i}. **Check number {i}** — description.")
    _write(
        tmp / ".claude" / "prompts" / "review.md",
        "\n".join(review) + "\n",
    )
    _write(
        tmp / "CLAUDE.md",
        """\
        **Safety-gate scope escalation (MUST):** any PR touching
        safety-gate scope (hooks, pre-commit checks, review gates, CI
        checks, merge guards, branch-protection-adjacent scripts,
        `.claude/skills/**/SKILL.md` edits) MUST additionally be shipped
        via `/coordinator`.

        ### CI (GitHub Actions, 9 + 1 extra) — runs on every push.

        9. `gate-9` — placeholder.
        """,
    )


# -- Authoritative count parsing ------------------------------------------


class TestAuthoritativeCount:
    """Rule A invariant: authoritative count = max of top-level numbered checks."""

    def test_parses_count_from_numbered_items(self, scanner: ModuleType, tmp_path: Path) -> None:
        _seed_repo(tmp_path, checks=22)
        assert scanner.compute_authoritative_check_count(tmp_path) == 22

    def test_fail_closed_on_missing_review_md(self, scanner: ModuleType, tmp_path: Path) -> None:
        # No review.md at all.
        with pytest.raises(RuntimeError, match="missing"):
            scanner.compute_authoritative_check_count(tmp_path)

    def test_fail_closed_on_empty_review_md(self, scanner: ModuleType, tmp_path: Path) -> None:
        _write(tmp_path / ".claude" / "prompts" / "review.md", "")
        with pytest.raises(RuntimeError, match="No numbered checks"):
            scanner.compute_authoritative_check_count(tmp_path)


# -- Rule A: claim drift --------------------------------------------------


class TestClaimDrift:
    def test_happy_matching_count(self, scanner: ModuleType, tmp_path: Path) -> None:
        _seed_repo(tmp_path, checks=22)
        _write(tmp_path / "DOC.md", "Walk checks 1-22 in review.md.\n")
        assert scanner.run(tmp_path) == 0

    def test_failure_en_dash_mismatch(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The en-dash (U+2013) variant must also be detected.
        _seed_repo(tmp_path, checks=22)
        _write(tmp_path / "DOC.md", "Walk checks 1\u201321 honestly.\n")
        exit_code = scanner.run(tmp_path)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "says 21, authoritative count is 22" in captured.err

    def test_failure_all_n_form(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed_repo(tmp_path, checks=22)
        _write(tmp_path / "DOC.md", "Walk all 21 checks honestly.\n")
        assert scanner.run(tmp_path) == 1
        assert "all 21 checks" in capsys.readouterr().err

    def test_adversarial_subrange_is_exempt(self, scanner: ModuleType, tmp_path: Path) -> None:
        # "Checks 1-13 and 22 always run. Checks 14-21 are conditional."
        # Neither sub-range is a total-count claim — rule A must not flag.
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "Checks 1-13 and 22 always run. Checks 14-21 are conditional.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_adversarial_quoted_example_is_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        # The scanner's own CLAUDE.md gate description quotes "checks 1-21"
        # as an example. Quoted/backticked occurrences are not live claims.
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            'Scans for stale claims like "checks 1-21" when authoritative is 22.\n',
        )
        assert scanner.run(tmp_path) == 0

    def test_adversarial_backticked_example_is_exempt(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "DOC.md",
            "Scans for stale claims like `checks 1-21` when authoritative is 22.\n",
        )
        assert scanner.run(tmp_path) == 0


# -- Rule B: retired terms ------------------------------------------------


class TestRetiredTerms:
    def test_happy_scoped_with_retired_marker(self, scanner: ModuleType, tmp_path: Path) -> None:
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "docs" / "history.md",
            "PaddleOCR is the single fallback (Tesseract retired — see ADR-013).\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_failure_bare_mention(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "docs" / "notes.md",
            "Consider adding Tesseract to the pipeline for hOCR evidence.\n",
        )
        assert scanner.run(tmp_path) == 1
        assert "tesseract" in capsys.readouterr().err.lower()

    def test_adversarial_grandfathered_adr_dir(self, scanner: ModuleType, tmp_path: Path) -> None:
        # ADR files legitimately name retired tech even without scoping.
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "docs" / "adrs" / "ADR-013-retire.md",
            "This ADR retires Tesseract from the pipeline.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_adversarial_scoping_marker_two_lines_above(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        # Marker may appear up to 2 lines before/after the match.
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "docs" / "story.md",
            textwrap.dedent(
                """\
                The OCR retirement decision in S5U-592 removed an
                entire tertiary layer from our fallback stack.
                Specifically, Tesseract is no longer invoked.
                """
            ),
        )
        assert scanner.run(tmp_path) == 0

    def test_adversarial_scoping_marker_too_far_away(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        # Marker more than 2 lines away does NOT exempt the match.
        _seed_repo(tmp_path, checks=22)
        _write(
            tmp_path / "docs" / "story.md",
            textwrap.dedent(
                """\
                The pipeline once used Tesseract for hOCR output.

                Today we use PaddleOCR.

                Four lines down, much later in the file, we mention
                that the retirement of legacy OCR paths happened.
                """
            ),
        )
        # "retired" keyword appears > 2 lines away from the "Tesseract" line.
        assert scanner.run(tmp_path) == 1


# -- Rule C: safety-gate scope enumeration --------------------------------


class TestSafetyGateScope:
    _CANONICAL_PARENTHETICAL = (
        "hooks, pre-commit checks, review gates, CI checks, merge guards, "
        "branch-protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits"
    )

    def _seed(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".claude" / "prompts" / "review.md",
            "## What to check\n\n"
            + "\n".join(f"{i}. **Check {i}** — x." for i in range(1, 23))
            + "\n",
        )
        _write(
            tmp_path / "CLAUDE.md",
            f"safety-gate scope ({self._CANONICAL_PARENTHETICAL}) canonical.\n\n"
            "### CI (GitHub Actions, 9 + 1 extra) — runs.\n\n"
            "9. `gate-9` — placeholder.\n",
        )

    def test_happy_skill_defers_to_claude_md(self, scanner: ModuleType, tmp_path: Path) -> None:
        self._seed(tmp_path)
        _write(
            tmp_path / ".claude" / "skills" / "ship" / "SKILL.md",
            "If any changed path matches safety-gate scope per CLAUDE.md "
            "(concrete paths: `.claude/hooks/**`), stop.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_happy_byte_equal_canonical(self, scanner: ModuleType, tmp_path: Path) -> None:
        self._seed(tmp_path)
        _write(
            tmp_path / ".claude" / "skills" / "ship" / "SKILL.md",
            f"safety-gate scope ({self._CANONICAL_PARENTHETICAL}) noted.\n",
        )
        assert scanner.run(tmp_path) == 0

    def test_failure_drifted_enumeration(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._seed(tmp_path)
        _write(
            tmp_path / ".claude" / "skills" / "ship" / "SKILL.md",
            "safety-gate scope (hooks only) — abbreviated list.\n",
        )
        assert scanner.run(tmp_path) == 1
        err = capsys.readouterr().err
        assert "safety-gate scope" in err
        assert "per CLAUDE.md" in err  # error message reminds the user of the escape hatch

    def test_adversarial_non_skill_file_not_scanned(
        self, scanner: ModuleType, tmp_path: Path
    ) -> None:
        # Rule C only applies to .claude/skills/**/SKILL.md and
        # .claude/prompts/**.md. A README.md with a divergent enumeration
        # is out of scope.
        self._seed(tmp_path)
        _write(
            tmp_path / "README.md",
            "safety-gate scope (hooks only, for README illustrative purposes).\n",
        )
        assert scanner.run(tmp_path) == 0


# -- Fail-closed integration ----------------------------------------------


class TestFailClosed:
    def test_missing_claude_md_is_fail_closed(
        self, scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(
            tmp_path / ".claude" / "prompts" / "review.md",
            "## What to check\n\n"
            + "\n".join(f"{i}. **Check {i}** — x." for i in range(1, 23))
            + "\n",
        )
        # No CLAUDE.md → canonical safety-gate extraction must fail-closed.
        assert scanner.run(tmp_path) == 1
        assert "FAIL-CLOSED" in capsys.readouterr().err

    def test_live_repo_passes(self, scanner: ModuleType) -> None:
        """Integration: the live repo itself must pass after S5U-658's drift fixes.
        This is the canonical red-before vehicle — before the drift fixes, the live
        repo scan returns exit=1."""
        # Red-before confirmation: at commit 00c9bff (branch creation point,
        # scanner absent AND drift present in CLAUDE.md:144 / SKILL.md:46 /
        # review.md:29), this test fails with ImportError (scanner absent).
        # With the scanner but without the drift fixes, run() returns 1 and
        # this assertion fails with the drift diagnostics printed to stderr.
        assert scanner.run(REPO) == 0

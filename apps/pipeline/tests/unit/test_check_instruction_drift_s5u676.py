"""Tests for S5U-676 — Rule A per-segment claim scanning.

S5U-667 introduced `_line_is_structural_subrange` which splits a line on
``[.;:]`` and exempts the **whole line** if **any** segment matches the
structural template. A crafted line with a stale claim in segment 1 and a
structural template in segment 2 (e.g.,
``When a new trigger fires, walk checks 1-21: Checks 1-13 always run.``)
bypasses Rule A.

S5U-676 fixes this with per-segment claim scanning: split each line on
``[.;:]``, scan each segment independently for claims, exempt only segments
whose form matches the structural template.

These tests pin the fix:

* §4a Happy — pure structural line (both segments structural) → exempt.
* §4b Failure — the issue's bypass line → exit 1.
* §4c Adversarial — comma-only mixed line (comma is not a splitter) → flag.
* §4d Empty segment (leading splitter) → no false positive.
* §4e Backtick exemption survives in segment context.
* §4f Claim in segment-1 + structural segment-2 → flag (the issue's class).
* §4g Structural-then-prose (semicolon splitter) → flag.

Red-before: tests committed first on branch
``s5unanow/s5u-676-drift-detector-segment-scan`` before the rule_a fix
landed. See the test-introduction commit SHA cited in commit B's message.
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


def _seed_repo(tmp: Path, *, checks: int = 25) -> None:
    """Seed a minimal fake repo with review.md + CLAUDE.md (with a CI section
    so Rule E's authoritative gate-count derivation succeeds)."""
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

            ### CI (GitHub Actions, 9 + 1 extra) — runs on every push.

            9. `gate-9` — placeholder.
            """
        ),
    )


# -- §4a Happy — pure structural line -------------------------------------


def test_pure_structural_line_with_period_splitter_exempt(
    scanner: ModuleType, tmp_path: Path
) -> None:
    """Both segments match the structural template → exempt."""
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "Checks 1-13 always run. Checks 14-21 are conditional.\n",
    )
    assert scanner.run(tmp_path) == 0


# -- §4b / §4f Failure — the issue's bypass line --------------------------


def test_bypass_line_from_issue_now_caught(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The S5U-676 reproducer: stale claim in prose segment, structural in
    second segment, split by `:`. Pre-fix this exempts the whole line.
    Post-fix segment-1 claim is detected.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "When a new trigger fires, walk checks 1-21: Checks 1-13 always run.\n",
    )
    assert scanner.run(tmp_path) == 1
    assert "says 21, authoritative count is 25" in capsys.readouterr().err


# -- §4c Adversarial — comma is not a splitter ----------------------------


def test_comma_separated_mixed_line_not_exempt(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Comma is not in the splitter set, so the whole line is one segment.
    The line as a whole does NOT match the anchored structural template
    (trailing prose breaks the regex), so the claim is flagged.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "Checks 1-13 always run, but walk checks 1-21 in edge cases.\n",
    )
    assert scanner.run(tmp_path) == 1
    assert "says 21, authoritative count is 25" in capsys.readouterr().err


# -- §4d Empty segment ----------------------------------------------------


def test_leading_splitter_empty_segment_no_false_positive(
    scanner: ModuleType, tmp_path: Path
) -> None:
    """Line with leading splitter produces an empty segment. Empty segment
    is non-structural by template, but also contains no claim — must not
    falsely flag.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        ". Checks 1-13 always run.\n",
    )
    assert scanner.run(tmp_path) == 0


# -- §4e Backtick exemption survives in segment context -------------------


def test_backtick_quoted_claim_in_segment_still_exempt(scanner: ModuleType, tmp_path: Path) -> None:
    """A claim inside backticks must remain exempt under per-segment
    scanning. The backtick-detection helper operates on the original line,
    so segment-relative offsets must be translated correctly.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "Walk `checks 1-21` for posterity.\n",
    )
    assert scanner.run(tmp_path) == 0


# -- §4g Structural-then-prose with semicolon splitter --------------------


def test_structural_then_prose_with_semicolon_splitter(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Segment 1 structural (exempt); segment 2 prose with stale claim
    (flagged). Pre-fix the whole line was exempted because segment 1
    matched.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "Checks 1-13 always run; we cover checks 1-21 in followup.\n",
    )
    assert scanner.run(tmp_path) == 1
    assert "says 21, authoritative count is 25" in capsys.readouterr().err


# -- Regression-pin — S5U-667 unbounded-substring class still blocked -----


def test_s5u667_pure_prose_substring_still_blocked(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S5U-667 regression: pure prose with `trigger` substring (no
    structural segment anywhere) must still be flagged. Pinning this here
    so the S5U-676 refactor doesn't regress S5U-667.
    """
    _seed_repo(tmp_path, checks=25)
    _write(
        tmp_path / "DOC.md",
        "When the review prompt gets a new trigger, walk checks 1-21 and note any mismatch.\n",
    )
    assert scanner.run(tmp_path) == 1
    assert "says 21, authoritative count is 25" in capsys.readouterr().err

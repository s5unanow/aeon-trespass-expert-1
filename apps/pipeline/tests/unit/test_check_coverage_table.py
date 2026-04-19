"""Parsing-layer tests for scripts/check_coverage_table.py (S5U-620).

Covers branch-name extraction, Linear bullet counting, PR body Coverage
section detection, table row counting, and deferred-ID extraction.

End-to-end `validate()` tests live in `test_check_coverage_table_validate.py`.

Three-input discipline (S5U-615) is applied to every test: each covers
happy-path, failure-input, and/or adversarial edge.

Red-before evidence: commit `<pre-fix SHA>^` of this test file was authored
against a production script whose fenced-code stripping was disabled
(probe 1) and whose HTML-comment stripping was disabled (probe 2). In both
probes, specific tests in this file failed with the expected assertion
errors; restoring the production code turned them green. See the S5U-620
PR body Red-before section for the pasted excerpts.
"""

from __future__ import annotations

import textwrap
from types import ModuleType

# NOTE: the `cct_mod` fixture (fresh import of scripts/check_coverage_table.py)
# is auto-discovered from apps/pipeline/tests/unit/conftest.py — no explicit
# import required.


# ----------------------------------------------------------------------
# Branch-name extraction
# ----------------------------------------------------------------------


class TestExtractIssueIdFromBranch:
    def test_happy_lowercase(self, cct_mod: ModuleType) -> None:
        assert cct_mod.extract_issue_id_from_branch("s5unanow/s5u-620-foo") == "620"

    def test_happy_uppercase(self, cct_mod: ModuleType) -> None:
        assert cct_mod.extract_issue_id_from_branch("s5unanow/S5U-1-bar") == "1"

    def test_failure_no_id(self, cct_mod: ModuleType) -> None:
        assert cct_mod.extract_issue_id_from_branch("main") is None

    def test_failure_malformed(self, cct_mod: ModuleType) -> None:
        assert cct_mod.extract_issue_id_from_branch("feature/random-branch") is None

    def test_adversarial_multiple_ids_first_wins(self, cct_mod: ModuleType) -> None:
        assert cct_mod.extract_issue_id_from_branch("s5unanow/s5u-620-refs-s5u-9") == "620"


# ----------------------------------------------------------------------
# Bullet counting
# ----------------------------------------------------------------------


class TestCountBullets:
    def test_counts_top_level_bullets(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - first
            - second
            - third
            """
        )
        result = cct_mod.count_bullets(desc)
        assert result.total == 3
        assert result.top_level == 3
        assert result.nested == 0

    def test_counts_nested_sub_bullets(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - parent
              - child-a
              - child-b
              - child-c
              - child-d
            """
        )
        result = cct_mod.count_bullets(desc)
        assert result.total == 5
        assert result.top_level == 1
        assert result.nested == 4

    def test_excludes_must_not_break_bullets(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - f1
            - f2
            - f3

            ## Must not break

            - mnb-1
            - mnb-2
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_excludes_fenced_code_block_bullets(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - real-1
            - real-2

            ```
            - fake-1
            - fake-2
            - fake-3
            ```

            - real-3
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_counts_success_criteria_section(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - f1

            ## Success criteria

            - s1
            - s2
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_fix_sketch_heading_recognized(self, cct_mod: ModuleType) -> None:
        # S5U-620's own Linear issue uses "Fix sketch" (bold-pseudo-heading).
        desc = textwrap.dedent(
            """
            **Fix sketch**

            - path A
            - path B
            - decision criterion
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_bold_pseudo_heading_recognized(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            **Fix**

            - one
            - two
            - three
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_star_markers_counted(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            * alpha
            * beta
            * gamma
            """
        )
        assert cct_mod.count_bullets(desc).total == 3

    def test_numbered_markers_counted(self, cct_mod: ModuleType) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            1. alpha
            2. beta
            3. gamma
            """
        )
        assert cct_mod.count_bullets(desc).total == 3


# ----------------------------------------------------------------------
# PR body parsing: Coverage section detection
# ----------------------------------------------------------------------


class TestFindCoverageSection:
    def test_happy_standard_heading(self, cct_mod: ModuleType) -> None:
        body = "## Coverage\n\n| # | X | Y |\n|---|---|---|\n| F1 | a | b |\n"
        section = cct_mod.find_coverage_section(body)
        assert section is not None
        assert "| F1 | a | b |" in section

    def test_case_insensitive(self, cct_mod: ModuleType) -> None:
        body = "## coverage\n\n| # | X | Y |\n"
        assert cct_mod.find_coverage_section(body) is not None

    def test_suffix_tolerant(self, cct_mod: ModuleType) -> None:
        body = "## Coverage Table\n\n| # | X |\n"
        assert cct_mod.find_coverage_section(body) is not None

    def test_heading_level_variants(self, cct_mod: ModuleType) -> None:
        for prefix in ("#", "##", "###", "####"):
            body = f"{prefix} Coverage\n\n| x |\n"
            assert cct_mod.find_coverage_section(body) is not None, f"failed for level {prefix!r}"

    def test_failure_no_coverage_section(self, cct_mod: ModuleType) -> None:
        body = "## Summary\n\nJust a summary.\n"
        assert cct_mod.find_coverage_section(body) is None

    def test_adversarial_html_commented_coverage_treated_as_absent(
        self, cct_mod: ModuleType
    ) -> None:
        body = "<!-- ## Coverage\n\n| F1 | ok |\n-->\n\n## Summary\n"
        assert cct_mod.find_coverage_section(body) is None


# ----------------------------------------------------------------------
# Table row counting
# ----------------------------------------------------------------------


class TestCountTableDataRows:
    def test_happy_three_rows(self, cct_mod: ModuleType) -> None:
        section = textwrap.dedent(
            """

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | a | x |
            | F2 | b | y |
            | F3 | c | z |
            """
        )
        assert cct_mod.count_table_data_rows(section) == 3

    def test_empty_table_zero_rows(self, cct_mod: ModuleType) -> None:
        section = textwrap.dedent(
            """

            | # | bullet |
            |---|--------|
            """
        )
        assert cct_mod.count_table_data_rows(section) == 0

    def test_adversarial_no_separator(self, cct_mod: ModuleType) -> None:
        # No separator -> `passed_separator` never flips -> zero rows.
        section = "| F1 | a | b |\n| F2 | c | d |\n"
        assert cct_mod.count_table_data_rows(section) == 0


# ----------------------------------------------------------------------
# Deferred ID extraction
# ----------------------------------------------------------------------


class TestExtractDeferredIssueIds:
    def test_happy_single_deferral(self, cct_mod: ModuleType) -> None:
        section = "| F3 | render tooltip | deferred to S5U-999 |"
        assert cct_mod.extract_deferred_issue_ids(section) == ["999"]

    def test_failure_no_defer_row(self, cct_mod: ModuleType) -> None:
        section = "| F1 | a | scripts/x.py |"
        assert cct_mod.extract_deferred_issue_ids(section) == []

    def test_adversarial_mentions_issue_without_defer_word(self, cct_mod: ModuleType) -> None:
        section = "| F1 | see S5U-123 for context | scripts/x.py |"
        assert cct_mod.extract_deferred_issue_ids(section) == []

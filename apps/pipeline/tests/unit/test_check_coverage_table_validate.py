"""End-to-end validate() tests for scripts/check_coverage_table.py (S5U-620).

Covers happy-path, failure inputs (missing section, row mismatch, bad
branch, missing API key), and adversarial edges (Canceled deferral,
non-existent deferral, HTML-wrapped table, Linear API error).

Red-before evidence: commit `<pre-fix SHA>^` — production script's
HTML-comment stripping in `find_coverage_section` was disabled and
`test_adversarial_html_comment_hides_coverage` failed with
`assert not True` (see S5U-620 PR body Red-before section).
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from types import ModuleType

# NOTE: `cct_mod` (module) and `cct_stub_fetcher` (factory) are auto-
# discovered fixtures from apps/pipeline/tests/unit/conftest.py.

StubFactory = Callable[[dict[str, tuple[str, str]]], object]


# ----------------------------------------------------------------------
# End-to-end validate() tests
# ----------------------------------------------------------------------


class TestValidate:
    def test_happy_compliant_pr(self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory) -> None:
        desc = textwrap.dedent(
            """
            ## Fix

            - first
            - second
            - third
            """
        )
        body = textwrap.dedent(
            """
            ## Summary
            ok

            ## Coverage

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | first  | a.py      |
            | F2 | second | b.py      |
            | F3 | third  | c.py      |
            """
        )
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert result.ok, result.message

    def test_failure_missing_coverage_section(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        desc = "## Fix\n\n- a\n- b\n- c\n"
        body = "## Summary\nno coverage here.\n"
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "lacks a '## Coverage' section" in result.message

    def test_failure_row_count_mismatch(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        # Issue has 5 bullets (1 parent + 4 nested), table has only 1 row.
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
        body = textwrap.dedent(
            """
            ## Coverage

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | parent (covers children) | x.py |
            """
        )
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "1 data row" in result.message
        assert "5 bullets" in result.message
        assert "S5U-622" in result.message

    def test_below_threshold_skips(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        desc = "## Fix\n\n- single\n- pair\n"  # 2 bullets
        body = "## Summary\nNo coverage table — below threshold.\n"
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert result.ok

    def test_adversarial_deferred_to_canceled_issue(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        desc = "## Fix\n\n- a\n- b\n- c\n"
        body = textwrap.dedent(
            """
            ## Coverage

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | a | x.py |
            | F2 | b | y.py |
            | F3 | c | deferred to S5U-999 |
            """
        )
        fetch = cct_stub_fetcher(
            {
                "620": (desc, "In Progress"),
                "999": ("", "Canceled"),
            },
        )
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "Canceled" in result.message

    def test_adversarial_deferred_to_nonexistent_issue(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        desc = "## Fix\n\n- a\n- b\n- c\n"
        body = textwrap.dedent(
            """
            ## Coverage

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | a | x.py |
            | F2 | b | y.py |
            | F3 | c | deferred to S5U-91919191 |
            """
        )
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "could not be verified" in result.message

    def test_failure_missing_api_key(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        fetch = cct_stub_fetcher({})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body="## Coverage\n\n| F1 | x |\n",
            api_key="",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "LINEAR_API_KEY not configured" in result.message

    def test_failure_bad_branch_name(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        fetch = cct_stub_fetcher({})
        result = cct_mod.validate(
            branch="random-branch-no-id",
            pr_body="irrelevant",
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "Cannot extract Linear issue ID" in result.message

    def test_failure_linear_api_error(self, cct_mod: ModuleType) -> None:
        LinearAPIError = cct_mod.LinearAPIError

        def raise_exc(issue_num: str, api_key: str) -> object:
            raise LinearAPIError("simulated rate-limit after retries")

        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body="whatever",
            api_key="lin_fake",
            fetch_issue=raise_exc,
        )
        assert not result.ok
        assert "fail-CLOSED" in result.message

    def test_adversarial_html_comment_hides_coverage(
        self, cct_mod: ModuleType, cct_stub_fetcher: StubFactory
    ) -> None:
        # Attacker wraps a fake Coverage section in an HTML comment and
        # replaces the visible body with a summary only — must fail.
        desc = "## Fix\n\n- a\n- b\n- c\n"
        body = textwrap.dedent(
            """
            <!--
            ## Coverage

            | # | bullet | addressed |
            |---|--------|-----------|
            | F1 | a | x |
            | F2 | b | y |
            | F3 | c | z |
            -->

            ## Summary
            brief summary only.
            """
        )
        fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
        result = cct_mod.validate(
            branch="s5unanow/s5u-620-foo",
            pr_body=body,
            api_key="lin_fake",
            fetch_issue=fetch,
        )
        assert not result.ok
        assert "lacks a '## Coverage' section" in result.message

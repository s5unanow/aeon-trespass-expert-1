"""Regex unit tests for `scripts/check_visual_gate_scope.py` (S5U-608).

S5U-655 split: extracted from the original 902-line file. Adds shell-
terminator coverage for `;`, `&`, `|`, `)`, `(`, `<`, `>`, `,` (issue
S5U-655 §a, three-input discipline per `.claude/rules/hooks.md`).
"""

from __future__ import annotations

from types import ModuleType

import pytest

# `scope` fixture is auto-discovered from `tests/unit/conftest.py` (S5U-655).


class TestForbiddenTokenRegex:
    def test_long_flag_detected(self, scope: ModuleType) -> None:
        assert scope._contains_forbidden_flag("playwright test --update-snapshots")

    def test_short_flag_detected(self, scope: ModuleType) -> None:
        assert scope._contains_forbidden_flag("playwright test -u")

    def test_ignore_flag_detected(self, scope: ModuleType) -> None:
        assert scope._contains_forbidden_flag("playwright test --ignore-snapshots")

    def test_equals_form_detected(self, scope: ModuleType) -> None:
        assert scope._contains_forbidden_flag("playwright test --update-snapshots=true")

    def test_quoted_short_flag_detected(self, scope: ModuleType) -> None:
        assert scope._contains_forbidden_flag("bash -c 'playwright test -u'")

    def test_user_flag_not_false_positive(self, scope: ModuleType) -> None:
        # `--user` must NOT trip the `-u` pattern.
        assert not scope._contains_forbidden_flag("some-tool --user")

    def test_update_substring_not_false_positive(self, scope: ModuleType) -> None:
        # A word like "my-update-snapshots-lib" must not match.
        assert not scope._contains_forbidden_flag("run: my-update-snapshots-lib --help")

    def test_plain_echo_not_false_positive(self, scope: ModuleType) -> None:
        assert not scope._contains_forbidden_flag('run: echo "tests complete"')


# -- S5U-655: shell-terminator class coverage -----------------------------
#
# The pre-S5U-655 trailing class was `[\s="'`]|$` — narrow. Real shell
# vectors using punctuation terminators (`;`, `&`, `|`, `)`, `(`, `<`,
# `>`, `,`) bypassed the matcher. S5U-655 broadens the leading and
# trailing classes to include these. Each terminator gets a happy-path
# (BLOCK) and false-positive guard (PASS) below per three-input
# discipline (`.claude/rules/hooks.md`).


class TestShellTerminatorBlocking:
    """Forbidden-flag matcher must catch every shell-terminator variant.

    Each input has the forbidden flag immediately followed by the new
    terminator (no intervening whitespace) so the test exercises the
    new char-class additions specifically; whitespace alone already
    matched pre-S5U-655.
    """

    @pytest.mark.parametrize(
        "input_str",
        [
            # `;` — issue worked example, terminator immediately after flag
            "pnpm exec playwright test -u; echo ok",
            # `&` — `&&` chain immediately after the flag
            "playwright test --update-snapshots&& echo ok",
            # `|` — pipe immediately after the flag (no whitespace)
            "pnpm exec playwright test -u|tee log",
            # `)` — issue worked example, subshell close
            "playwright test --ignore-snapshots)",
            # `(` — leading paren before the flag (subshell open)
            "(playwright test -u)",
            # `<` — input redirect immediately after the flag
            "playwright test -u<input.txt",
            # `>` — output redirect immediately after the flag
            "playwright test --update-snapshots>out.log",
            # `,` — comma-separated arg list, e.g. bash array
            "args=(--update-snapshots,--reporter=html)",
        ],
        ids=[
            "semicolon",
            "ampersand",
            "pipe",
            "rparen",
            "lparen",
            "lt-redir",
            "gt-redir",
            "comma",
        ],
    )
    def test_shell_terminator_blocks_forbidden_flag(
        self, scope: ModuleType, input_str: str
    ) -> None:
        assert scope._contains_forbidden_flag(input_str)


class TestShellTerminatorFalsePositiveGuards:
    """Adversarial inputs: terminator present but no forbidden flag."""

    @pytest.mark.parametrize(
        "input_str",
        [
            # Substring match on `--update-snapshots`: extended via dash
            "tee --update-snapshots-log",
            # `;` present but no forbidden flag
            "echo no flag here; ok",
            # `(` wraps an unrelated `--update` substring (no `--update-snapshots`)
            "(echo --update)",
            # `<` redir alone, no flag
            "<input.txt",
            # `,` separator with non-forbidden args
            "args=(--user,--bar)",
            # `&&` chain between unrelated commands
            "pnpm install && echo done",
            # `)` close of an unrelated subshell
            "(echo done)",
        ],
        ids=[
            "dash-substring",
            "semicolon-no-flag",
            "lparen-unrelated",
            "lt-only",
            "comma-no-flag",
            "amp-no-flag",
            "rparen-no-flag",
        ],
    )
    def test_shell_terminator_no_false_positive(self, scope: ModuleType, input_str: str) -> None:
        assert not scope._contains_forbidden_flag(input_str)

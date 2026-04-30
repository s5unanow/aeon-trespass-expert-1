"""Regex unit tests for `scripts/check_visual_gate_scope.py` (S5U-608).

S5U-655 split: extracted from the original 902-line file.
"""

from __future__ import annotations

from types import ModuleType

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

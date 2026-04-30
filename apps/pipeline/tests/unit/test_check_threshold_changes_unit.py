"""Unit tests for scripts/check_threshold_changes.py pure helpers.

S5U-656 split-out from the original test_check_threshold_changes.py: the
pure-helper unit tests (no subprocess) live here. The companion E2E tests
live in test_check_threshold_changes_e2e_happy.py and
test_check_threshold_changes_e2e_bypass.py. The shared `guard` fixture
(loads check_threshold_changes.py as a module) is defined in conftest.py.

S5U-643 per-finding tests (responsible-commit resolution + named-threshold
sentinel) carry red-before evidence. The pre-S5U-643 baseline lives at
`/tmp/s5u-643-redbefore/check_threshold_changes_baseline.py` (snapshot of
`scripts/check_threshold_changes.py` at SHA `cbd0256`). Running the new
adversarial tests against that baseline demonstrates the old free-form
sentinel accepts the decoy-commit-A / silent-loosen-commit-B exploit
that S5U-643 now blocks.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

TOML_BASE = """\
version = 1

[[metric_thresholds]]
name = "a_pass_rate"
min = 0.98
blocking = true
description = "A"

[[metric_thresholds]]
name = "b_pass_rate"
min = 0.90
blocking = true
description = "B"
"""


class TestParseThresholds:
    def test_missing_file_returns_empty(self, guard: ModuleType) -> None:
        assert guard._parse_thresholds(None) == {}

    def test_well_formed_returns_entries(self, guard: ModuleType) -> None:
        parsed = guard._parse_thresholds(TOML_BASE)
        assert set(parsed.keys()) == {"a_pass_rate", "b_pass_rate"}
        assert parsed["a_pass_rate"].min == 0.98
        assert parsed["a_pass_rate"].blocking is True

    def test_entry_without_name_skipped(self, guard: ModuleType) -> None:
        toml = '[[metric_thresholds]]\nmin = 0.9\n\n[[metric_thresholds]]\nname = "ok"\nmin = 0.8\n'
        assert set(guard._parse_thresholds(toml).keys()) == {"ok"}

    def test_entry_without_min_skipped(self, guard: ModuleType) -> None:
        toml = (
            '[[metric_thresholds]]\nname = "no_min"\n\n'
            '[[metric_thresholds]]\nname = "ok"\nmin = 0.8\n'
        )
        assert set(guard._parse_thresholds(toml).keys()) == {"ok"}

    def test_malformed_toml_raises(self, guard: ModuleType) -> None:
        with pytest.raises(SystemExit):
            guard._parse_thresholds("this is {{{ not valid TOML")

    @pytest.mark.parametrize(
        "blocking_value",
        ['"false"', '"true"', "1", "0"],
        ids=["str-false", "str-true", "int-1", "int-0"],
    )
    def test_blocking_non_bool_rejected(self, guard: ModuleType, blocking_value: str) -> None:
        """S5U-644: string "false" (truthy), "true", int 1/0 all must raise."""
        toml = f'[[metric_thresholds]]\nname = "x"\nmin = 0.5\nblocking = {blocking_value}\n'
        with pytest.raises(SystemExit, match="must be a TOML boolean"):
            guard._parse_thresholds(toml)


class TestDetectLoosening:
    def test_identical_no_findings(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        assert guard.detect_loosening(base, dict(base)) == []

    def test_min_lowered_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.80, blocking=True)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].name == "a_pass_rate"
        assert findings[0].kind == "min_lowered"

    def test_min_raised_no_finding(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.99, blocking=True)
        assert guard.detect_loosening(base, head) == []

    def test_entry_deleted_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = {k: v for k, v in base.items() if k != "b_pass_rate"}
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].kind == "deleted"

    def test_blocking_flip_to_false_detected(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.98, blocking=False)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].kind == "blocking_disabled"

    def test_net_new_entry_no_finding(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["c_new"] = guard.ThresholdEntry(name="c_new", min=0.5, blocking=True)
        assert guard.detect_loosening(base, head) == []

    def test_tighten_plus_loosen_reports_loosen(self, guard: ModuleType) -> None:
        base = guard._parse_thresholds(TOML_BASE)
        head = dict(base)
        head["a_pass_rate"] = guard.ThresholdEntry(name="a_pass_rate", min=0.99, blocking=True)
        head["b_pass_rate"] = guard.ThresholdEntry(name="b_pass_rate", min=0.50, blocking=True)
        findings = guard.detect_loosening(base, head)
        assert len(findings) == 1
        assert findings[0].name == "b_pass_rate"


class TestCommitSentinelCovers:
    """S5U-643: per-finding, named sentinel matching."""

    @pytest.mark.parametrize(
        "sep",
        ["—", "--", "-", ":"],
        ids=["em-dash", "double-hyphen", "hyphen", "colon"],
    )
    def test_named_threshold_with_any_valid_separator_matches(
        self, guard: ModuleType, sep: str
    ) -> None:
        """S5U-643: all four separator forms accepted (`—`, `--`, `-`, `:`)."""
        msg = f"LOOSEN-THRESHOLD: a_pass_rate {sep} dataset refresh"
        ok, reason = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is True
        assert "dataset refresh" in reason

    def test_case_insensitive_sentinel(self, guard: ModuleType) -> None:
        msg = "loosen-threshold: A_Pass_Rate — dataset refresh"
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is True

    def test_multi_name_list_covers_each(self, guard: ModuleType) -> None:
        msg = "LOOSEN-THRESHOLD: a_pass_rate, b_pass_rate — joint recalibration"
        assert guard.commit_sentinel_covers("a_pass_rate", msg)[0] is True
        assert guard.commit_sentinel_covers("b_pass_rate", msg)[0] is True

    def test_wrong_threshold_name_rejected(self, guard: ModuleType) -> None:
        """S5U-643: sentinel naming a different threshold does not cover ours."""
        msg = "LOOSEN-THRESHOLD: a_pass_rate — reason"
        ok, _ = guard.commit_sentinel_covers("b_pass_rate", msg)
        assert ok is False

    def test_free_form_no_name_rejected(self, guard: ModuleType) -> None:
        """S5U-643: the old `LOOSEN-THRESHOLD: <reason>` grammar is retired.

        Red-before confirmation: ran
        `/tmp/s5u-643-redbefore/check_threshold_changes_baseline.py`'s
        `has_commit_sentinel(["LOOSEN-THRESHOLD: recalibrated"])` → returned
        (True, 'recalibrated'). The new `commit_sentinel_covers('a_pass_rate',
        ...)` returns (False, '') for the same input, enforcing per-finding
        binding.
        """
        msg = "LOOSEN-THRESHOLD: recalibrated"
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is False

    def test_empty_reason_rejected(self, guard: ModuleType) -> None:
        msg = "LOOSEN-THRESHOLD: a_pass_rate —   "
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", msg)
        assert ok is False

    def test_missing_sentinel(self, guard: ModuleType) -> None:
        ok, _ = guard.commit_sentinel_covers("a_pass_rate", "S5U-XXX: normal commit")
        assert ok is False


class TestPrBodyCovers:
    @staticmethod
    def _write(tmp_path: Path, body: str) -> Path:
        f = tmp_path / "pr_body.md"
        f.write_text(body)
        return f

    def test_bullet_matches(self, guard: ModuleType, tmp_path: Path) -> None:
        body = (
            "## Summary\n\nChange.\n\n"
            "## Threshold loosening justification\n\n"
            "- a_pass_rate: dataset recalibrated 2026-04-10\n"
            "- b_pass_rate: see audit report\n"
        )
        f = self._write(tmp_path, body)
        ok, reason = guard.pr_body_covers("a_pass_rate", f)
        assert ok is True
        assert "recalibrated" in reason
        assert guard.pr_body_covers("b_pass_rate", f)[0] is True

    def test_bullet_for_different_threshold_rejected(
        self, guard: ModuleType, tmp_path: Path
    ) -> None:
        """S5U-643: coverage is per-finding; bullets for other names don't help."""
        f = self._write(tmp_path, "## Threshold loosening justification\n\n- a_pass_rate: reason\n")
        assert guard.pr_body_covers("b_pass_rate", f)[0] is False

    def test_heading_without_bullets_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        f = self._write(tmp_path, "## Threshold loosening justification\n\n## Next section\n")
        assert guard.pr_body_covers("a_pass_rate", f)[0] is False

    def test_bullet_outside_section_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        """S5U-643: bullets must be under the designated heading, not elsewhere."""
        body = (
            "## Other section\n\n- a_pass_rate: reason\n\n"
            "## Threshold loosening justification\n\n(empty)\n"
        )
        assert guard.pr_body_covers("a_pass_rate", self._write(tmp_path, body))[0] is False

    def test_missing_file_rejected(self, guard: ModuleType, tmp_path: Path) -> None:
        assert guard.pr_body_covers("a_pass_rate", tmp_path / "nope.md")[0] is False

    def test_none_path_rejected(self, guard: ModuleType) -> None:
        assert guard.pr_body_covers("a_pass_rate", None)[0] is False

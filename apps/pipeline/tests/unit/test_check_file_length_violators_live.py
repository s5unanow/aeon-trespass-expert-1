"""Tests for scripts/check_file_length_violators_live.py (S5U-669).

The live check validates every ``KNOWN_VIOLATORS`` value in
``scripts/check_file_length.py`` resolves to a non-Done / non-Canceled
Linear issue. Fail-closed on missing secret, malformed Linear ID, API
error, or rate-limit (inherited from ``_linear_client``).

Three-input adversarial coverage per ``.claude/rules/hooks.md`` and
``.claude/rules/guards.md`` Rule G1:

* Happy path — every value resolves to an open state (``backlog`` / ``started``)
* Failure input — a value resolves to ``completed`` or ``canceled`` → exit 1
* Adversarial edges — missing secret, malformed ID, LinearAPIError,
  deduplication of identical IDs, tolerance of ``"unknown"`` state
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_file_length_violators_live.py"
CFL_PATH = REPO / "scripts" / "check_file_length.py"


@pytest.fixture()
def live(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import ``check_file_length_violators_live`` as a module.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814
    (pre-fix main HEAD) — ``SCRIPT_PATH`` did not exist; this fixture
    raises ``FileNotFoundError`` / ``AttributeError`` before the fix
    adds the script and the module import succeeds.
    """
    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parent))
    spec = importlib.util.spec_from_file_location("check_file_length_violators_live", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_file_length_violators_live"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_file_length_violators_live", None)


def _make_issue(
    live_mod: ModuleType,
    identifier: str,
    state_type: str,
    state_name: str | None = None,
) -> object:
    """Construct a ``LinearIssue`` with the given state."""
    return live_mod.LinearIssue(
        identifier=identifier,
        description="",
        state_name=state_name or state_type.capitalize(),
        state_type=state_type,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_all_open_state_types_pass(live: ModuleType) -> None:
    """Values resolving to ``backlog`` / ``started`` / ``unstarted`` / ``triage``
    all pass.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    ``scan`` did not exist; the test fails at import time.
    """
    fetched: list[str] = []

    def fake_fetch(number: str, api_key: str) -> object:
        fetched.append(number)
        return _make_issue(live, f"S5U-{number}", "backlog")

    violators = {
        "foo.py": "S5U-100",
        "bar.py": "S5U-200",
    }
    violations = live.scan(violators, api_key="fake", fetch_issue=fake_fetch)
    assert violations == []
    assert sorted(fetched) == ["100", "200"]


def test_dedupes_identical_issue_ids(live: ModuleType) -> None:
    """Multiple paths mapping to the same Linear ID fetch the issue once.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    ``_group_paths_by_issue`` / ``scan`` did not exist; test fails at
    import time.
    """
    fetched: list[str] = []

    def fake_fetch(number: str, api_key: str) -> object:
        fetched.append(number)
        return _make_issue(live, f"S5U-{number}", "backlog")

    # 12 paths, all keyed to the same umbrella issue.
    violators = {f"path_{i}.py": "S5U-677" for i in range(12)}
    violations = live.scan(violators, api_key="fake", fetch_issue=fake_fetch)
    assert violations == []
    # Dedup: one Linear fetch regardless of path count.
    assert fetched == ["677"], f"expected single fetch, got {fetched}"


def test_unknown_state_type_is_tolerated(live: ModuleType) -> None:
    """An ``"unknown"`` state passes — schema-evolution safety (new Linear
    enum value must not retroactively break the gate).

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    ``STALE_STATE_TYPES`` did not exist; the test fails at import.
    """

    def fake_fetch(number: str, api_key: str) -> object:
        return _make_issue(live, f"S5U-{number}", "unknown", state_name="MysteryState")

    violations = live.scan({"foo.py": "S5U-999"}, api_key="fake", fetch_issue=fake_fetch)
    assert violations == []


# ---------------------------------------------------------------------------
# Failure paths (stale citations)
# ---------------------------------------------------------------------------


def test_done_issue_is_flagged(live: ModuleType) -> None:
    """A Linear issue with ``state_type == "completed"`` fails the check.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    the gate does not exist; closed-issue citations slip through silently.
    """

    def fake_fetch(number: str, api_key: str) -> object:
        return _make_issue(live, f"S5U-{number}", "completed", state_name="Done")

    violators = {
        "apps/pipeline/tests/unit/test_export_to_web.py": "S5U-663",
        "apps/pipeline/tests/unit/test_export_qa.py": "S5U-663",
    }
    violations = live.scan(violators, api_key="fake", fetch_issue=fake_fetch)
    assert len(violations) == 1
    v = violations[0]
    assert v.issue_id == "S5U-663"
    assert "completed" in v.reason
    assert v.affected_paths == [
        "apps/pipeline/tests/unit/test_export_qa.py",
        "apps/pipeline/tests/unit/test_export_to_web.py",
    ]


def test_canceled_issue_is_flagged(live: ModuleType) -> None:
    """A Linear issue with ``state_type == "canceled"`` fails the check.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    gate does not exist.
    """

    def fake_fetch(number: str, api_key: str) -> object:
        return _make_issue(live, f"S5U-{number}", "canceled", state_name="Canceled")

    violations = live.scan({"foo.py": "S5U-500"}, api_key="fake", fetch_issue=fake_fetch)
    assert len(violations) == 1
    assert violations[0].issue_id == "S5U-500"
    assert "canceled" in violations[0].reason


def test_mixed_open_and_closed_reports_only_closed(live: ModuleType) -> None:
    """An open and a closed citation in the same map: only the closed one flags.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    gate does not exist.
    """

    def fake_fetch(number: str, api_key: str) -> object:
        state_type = "completed" if number == "999" else "backlog"
        return _make_issue(live, f"S5U-{number}", state_type)

    violators = {
        "open.py": "S5U-100",
        "closed.py": "S5U-999",
    }
    violations = live.scan(violators, api_key="fake", fetch_issue=fake_fetch)
    assert len(violations) == 1
    assert violations[0].issue_id == "S5U-999"


# ---------------------------------------------------------------------------
# G1 fail-closed: missing secret, malformed ID, API error
# ---------------------------------------------------------------------------


def test_missing_api_key_fails_closed(live: ModuleType) -> None:
    """Empty ``LINEAR_API_KEY`` → single Violation with empty issue_id.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    gate does not exist; missing secret has no effect.
    """

    def never_called(number: str, api_key: str) -> object:
        raise AssertionError("fetch_issue must not be called when api_key is empty")

    violators = {"foo.py": "S5U-100"}
    violations = live.scan(violators, api_key="", fetch_issue=never_called)
    assert len(violations) == 1
    assert violations[0].issue_id == ""
    assert "LINEAR_API_KEY" in violations[0].reason
    assert violations[0].affected_paths == ["foo.py"]


def test_malformed_issue_id_fails_closed(live: ModuleType) -> None:
    """A KNOWN_VIOLATORS value that doesn't match ``^S5U-\\d+$`` fails.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    gate does not exist; nothing validates the value format.
    """

    def fake_fetch(number: str, api_key: str) -> object:
        raise AssertionError("fetch_issue must not be called for malformed IDs")

    violators = {
        "foo.py": "TBD",
        "bar.py": "OTHER-123",
        "baz.py": "",
    }
    violations = live.scan(violators, api_key="fake", fetch_issue=fake_fetch)
    assert len(violations) == 3
    reasons = {v.issue_id: v.reason for v in violations}
    assert "TBD" in reasons
    assert "OTHER-123" in reasons
    assert "" in reasons
    for reason in reasons.values():
        assert "Unparseable" in reason


def test_linear_api_error_fails_closed(live: ModuleType) -> None:
    """A ``LinearAPIError`` from ``fetch_issue`` surfaces as a Violation.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    gate does not exist.
    """
    from _linear_client import LinearAPIError

    def fake_fetch(number: str, api_key: str) -> object:
        raise LinearAPIError(f"Linear HTTP 404: Not Found for S5U-{number}")

    violations = live.scan({"foo.py": "S5U-100"}, api_key="fake", fetch_issue=fake_fetch)
    assert len(violations) == 1
    assert violations[0].issue_id == "S5U-100"
    assert "fail-CLOSED" in violations[0].reason
    assert "404" in violations[0].reason


# ---------------------------------------------------------------------------
# Integration: real KNOWN_VIOLATORS dict loads from the real script path
# ---------------------------------------------------------------------------


def test_load_known_violators_from_real_script(live: ModuleType) -> None:
    """Loading ``KNOWN_VIOLATORS`` from the real ``check_file_length.py`` works
    and contains the expected test-file entries after S5U-669 re-keying.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    the loader function does not exist in the script (which itself does
    not exist).
    """
    violators = live._load_known_violators(CFL_PATH)
    assert isinstance(violators, dict)
    # Spot-check a few entries — post-S5U-669, test_export_to_web.py maps
    # to S5U-677 (umbrella), not S5U-663.
    export_to_web = "apps/pipeline/tests/unit/test_export_to_web.py"
    actual = violators.get(export_to_web)
    assert actual == "S5U-677", f"expected re-key to S5U-677, got {actual!r}"
    # S5U-655 and S5U-656 untouched.
    assert violators["apps/pipeline/tests/unit/test_check_visual_gate_scope.py"] == "S5U-655"
    assert violators["apps/pipeline/tests/unit/test_check_threshold_changes.py"] == "S5U-656"


def test_load_known_violators_missing_attribute_fails_closed(
    live: ModuleType, tmp_path: Path
) -> None:
    """If the script has no ``KNOWN_VIOLATORS`` attribute, loader raises.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    the loader does not exist.
    """
    broken = tmp_path / "broken.py"
    broken.write_text("SOMETHING_ELSE = {}\n")
    with pytest.raises(RuntimeError, match="KNOWN_VIOLATORS"):
        live._load_known_violators(broken)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def test_format_report_lists_affected_paths(live: ModuleType) -> None:
    """The report includes the reason, issue ID, and every affected path.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    the formatter does not exist.
    """
    violation = live.Violation(
        issue_id="S5U-663",
        reason="Linear issue S5U-663 is 'Done' (state_type='completed')",
        affected_paths=["a.py", "b.py"],
    )
    report = live.format_report([violation])
    assert "S5U-663" in report
    assert "a.py" in report
    assert "b.py" in report
    assert "completed" in report


# ---------------------------------------------------------------------------
# CLI integration: main() exit codes
# ---------------------------------------------------------------------------


def test_main_returns_1_when_secret_missing(
    live: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``main()`` exits 1 when LINEAR_API_KEY is unset.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    ``main`` does not exist.
    """
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    code = live.main(["--check-file-length-path", str(CFL_PATH)])
    assert code == 1
    captured = capsys.readouterr()
    assert "LINEAR_API_KEY" in captured.err


def test_main_returns_1_when_script_path_missing(
    live: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``main()`` exits 1 when the check_file_length.py path does not exist.

    Red-before confirmation: commit bb8502f9e8b1ce7f6058b0e620553ac3ec259814 —
    ``main`` does not exist.
    """
    missing = tmp_path / "no-such-file.py"
    code = live.main(["--check-file-length-path", str(missing)])
    assert code == 1
    captured = capsys.readouterr()
    assert "cannot load" in captured.err.lower()

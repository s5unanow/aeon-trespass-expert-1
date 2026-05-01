"""Shared pytest fixtures for unit tests (S5U-620 coverage-table helpers).

Pytest auto-discovers fixtures defined here; test modules in this directory
can request them by name without an explicit import.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
_CCT_SCRIPT_PATH = SCRIPT_DIR / "check_coverage_table.py"


def _load_cct_module() -> ModuleType:
    """Import scripts/check_coverage_table.py as a fresh module.

    Ensures `scripts/` is on sys.path so the `_linear_client` sibling
    import inside `check_coverage_table.py` resolves.
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_coverage_table", _CCT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_coverage_table"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cct_mod() -> Iterator[ModuleType]:
    """Fresh import of check_coverage_table.py per test."""
    module = _load_cct_module()
    yield module
    sys.modules.pop("check_coverage_table", None)


# ---------------------------------------------------------------------------
# check_post_merge_coordinator_ack module-loader fixture (S5U-693)
# ---------------------------------------------------------------------------

_PMA_SCRIPT_PATH = SCRIPT_DIR / "check_post_merge_coordinator_ack.py"


@pytest.fixture()
def mod() -> Iterator[ModuleType]:
    """Load check_post_merge_coordinator_ack as a module for unit-testing.

    Name is deliberately generic (`mod`) because the fixture is only used by
    the two S5U-693 test files and keeping the test bodies readable matters
    more than the fixture namespace here.

    Side effect (S5U-728): the fixture replaces `module.time.sleep` with a
    no-op for the duration of the test so retry-with-backoff in
    `fetch_pull_numbers_for_commit` does not burn real wall-clock seconds.
    Tests that need to observe sleep calls must explicitly inject a `sleeper`
    callable or `patch.object(mod.time, "sleep", side_effect=...)` themselves
    (the explicit patch overrides the fixture's no-op for the patch's scope).
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "check_post_merge_coordinator_ack", _PMA_SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_post_merge_coordinator_ack"] = module
    spec.loader.exec_module(module)
    # Replace the module-level `time` reference with a stand-in whose
    # `sleep` is a no-op. We must NOT mutate the global `time` module; we
    # rebind only this module's `time` attribute.
    import time as _real_time
    from types import SimpleNamespace

    real_time_module = module.time
    module.time = SimpleNamespace(sleep=lambda _seconds: None, _real=_real_time)
    try:
        yield module
    finally:
        module.time = real_time_module
        sys.modules.pop("check_post_merge_coordinator_ack", None)


# ---------------------------------------------------------------------------
# check_threshold_changes module-loader fixture (S5U-656 split-out)
# ---------------------------------------------------------------------------

_CTC_SCRIPT_PATH = SCRIPT_DIR / "check_threshold_changes.py"


@pytest.fixture()
def guard() -> Iterator[ModuleType]:
    """Load scripts/check_threshold_changes.py as a fresh module per test.

    Used by the S5U-656 split unit-test files
    (test_check_threshold_changes_unit.py).
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_threshold_changes", _CTC_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_threshold_changes"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("check_threshold_changes", None)


# ---------------------------------------------------------------------------
# check_visual_gate_scope module-loader fixture (S5U-655 split-out)
# ---------------------------------------------------------------------------

_CVGS_SCRIPT_PATH = SCRIPT_DIR / "check_visual_gate_scope.py"


@pytest.fixture()
def scope(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/check_visual_gate_scope.py as a fresh module per test.

    Used by the S5U-655 split test files
    (test_check_visual_gate_scope_*.py).
    """
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_visual_gate_scope", _CVGS_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_visual_gate_scope"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("check_visual_gate_scope", None)


# ---------------------------------------------------------------------------
# check_visual_test_overrides module-loader fixture (S5U-657)
# ---------------------------------------------------------------------------

_CVTO_SCRIPT_PATH = SCRIPT_DIR / "check_visual_test_overrides.py"


@pytest.fixture()
def overrides_mod(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/check_visual_test_overrides.py as a fresh module per test.

    Used by the S5U-657 split test files
    (test_check_visual_test_overrides_*.py).
    """
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_visual_test_overrides", _CVTO_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_visual_test_overrides"] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("check_visual_test_overrides", None)


@pytest.fixture()
def cct_stub_fetcher(
    cct_mod: ModuleType,
) -> callable:  # type: ignore[valid-type]
    """Factory: build a deterministic `fetch_issue` stub.

    Usage:
        def test_x(cct_mod, cct_stub_fetcher):
            fetch = cct_stub_fetcher({"620": (desc, "In Progress")})
    """
    LinearIssue = cct_mod.LinearIssue
    LinearAPIError = cct_mod.LinearAPIError

    def factory(by_id: dict[str, tuple[str, str]]) -> object:
        def fake(issue_num: str, api_key: str) -> object:
            if issue_num not in by_id:
                raise LinearAPIError(f"Linear issue S5U-{issue_num} not found")
            description, state = by_id[issue_num]
            return LinearIssue(
                identifier=f"S5U-{issue_num}",
                description=description,
                state_name=state,
            )

        return fake

    return factory

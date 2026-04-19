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

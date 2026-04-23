"""Tests for scripts/check_branch_protection.py (S5U-709)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_branch_protection.py"


@pytest.fixture()
def mod() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("check_branch_protection", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_branch_protection"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("check_branch_protection", None)


def _write_workflow(root: Path, relative_path: str, body: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def test_parse_repo_slug_accepts_https_and_ssh(mod: ModuleType) -> None:
    assert mod.parse_repo_slug("https://github.com/s5unanow/aeon-trespass-expert-1.git") == (
        "s5unanow/aeon-trespass-expert-1"
    )
    assert mod.parse_repo_slug("git@github.com:s5unanow/aeon-trespass-expert-1.git") == (
        "s5unanow/aeon-trespass-expert-1"
    )


def test_collect_expected_contexts_expands_reusable_workflow_calls(
    mod: ModuleType, tmp_path: Path
) -> None:
    _write_workflow(
        tmp_path,
        ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "on:\n"
            "  pull_request:\n"
            "    branches: [main]\n"
            "jobs:\n"
            "  python:\n"
            "    uses: ./.github/workflows/python-tests.yml\n"
        ),
    )
    _write_workflow(
        tmp_path,
        ".github/workflows/python-tests.yml",
        (
            "name: Python Tests\n"
            "on:\n"
            "  workflow_call:\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n"
        ),
    )
    contexts = mod.collect_expected_contexts(tmp_path)
    assert contexts == frozenset({"python / test"})


def test_collect_expected_contexts_includes_direct_pull_request_job_name(
    mod: ModuleType, tmp_path: Path
) -> None:
    _write_workflow(
        tmp_path,
        ".github/workflows/coverage-table-scan.yml",
        (
            "name: Coverage Table Scan\n"
            "on:\n"
            "  pull_request:\n"
            "    branches: [main]\n"
            "jobs:\n"
            "  scan:\n"
            "    name: coverage-table-scan / scan\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n"
        ),
    )
    contexts = mod.collect_expected_contexts(tmp_path)
    assert contexts == frozenset({"coverage-table-scan / scan"})


def test_collect_expected_contexts_matches_current_repo_surface(mod: ModuleType) -> None:
    assert mod.collect_expected_contexts(REPO) == frozenset(
        {
            "coverage-table-scan / scan",
            "python / test",
            "visual-gate-scope / scan",
            "visual-regression / visual",
            "web / test",
        }
    )


def test_extract_live_protection_fails_closed_on_missing_admin_state(
    mod: ModuleType,
) -> None:
    payload = {
        "required_status_checks": {
            "strict": True,
            "contexts": ["python / test"],
        }
    }
    with pytest.raises(RuntimeError, match="enforce_admins"):
        mod.extract_live_protection(payload)


def test_audit_flags_admin_and_context_mismatch(mod: ModuleType, tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "on:\n"
            "  pull_request:\n"
            "    branches: [main]\n"
            "jobs:\n"
            "  python:\n"
            "    uses: ./.github/workflows/python-tests.yml\n"
        ),
    )
    _write_workflow(
        tmp_path,
        ".github/workflows/python-tests.yml",
        (
            "name: Python Tests\n"
            "on:\n"
            "  workflow_call:\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ok\n"
        ),
    )
    live = mod.LiveProtection(
        strict=False,
        enforce_admins=False,
        contexts=frozenset({"web / test"}),
    )
    findings = mod.audit(tmp_path, live)
    assert "required_status_checks.strict is false; branch freshness is not enforced" in findings
    assert "enforce_admins.enabled is false; admins can bypass required checks" in findings
    assert "missing required context(s): python / test" in findings
    assert "unexpected required context(s): web / test" in findings

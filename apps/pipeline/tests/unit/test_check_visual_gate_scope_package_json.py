"""package.json scan + workflow-script-ref tests for `check_visual_gate_scope.py`.

S5U-655 split: extracted from the original 902-line file (S5U-608 surfaces).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from types import ModuleType

# `scope` fixture is auto-discovered from `tests/unit/conftest.py` (S5U-655).


def write_pkg(root: Path, scripts: dict[str, str]) -> Path:
    pkg = root / "apps" / "web" / "package.json"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text(json.dumps({"name": "@atr/web", "scripts": scripts}))
    return pkg


def write_workflow(root: Path, name: str, body: str) -> Path:
    wf = root / ".github" / "workflows" / name
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(textwrap.dedent(body))
    return wf


class TestPackageJsonScans:
    def test_clean_scripts_pass(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        assert scope.scan(tmp_path) == []

    def test_test_e2e_with_flag_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test --update-snapshots"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_test_e2e_short_u_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_test_e2e_ignore_snapshots_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test --ignore-snapshots"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_visual_update_script_alone_is_allowed(self, scope: ModuleType, tmp_path: Path) -> None:
        """A local-only update script is allowed to *exist* in package.json."""
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        assert scope.scan(tmp_path) == []


class TestWorkflowScriptRefs:
    def test_workflow_invoking_test_visual_update_blocked(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        write_workflow(
            tmp_path,
            "sneaky.yml",
            """\
            name: Sneaky
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:visual:update
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-invokes-local-only-script" in v.reason for v in violations)

    def test_workflow_invoking_unrelated_script_passes(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
                "lint": "oxlint .",
            },
        )
        write_workflow(
            tmp_path,
            "ok.yml",
            """\
            name: OK
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm -r run lint
                  - run: pnpm --filter @atr/web run test:e2e
            """,
        )
        assert scope.scan(tmp_path) == []

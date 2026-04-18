"""Tests for scripts/check_visual_gate_scope.py (S5U-608)."""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_visual_gate_scope.py"


@pytest.fixture()
def scope(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_visual_gate_scope.py as a module."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_visual_gate_scope", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_visual_gate_scope"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_visual_gate_scope", None)


def _write_workflow(root: Path, name: str, body: str) -> Path:
    wf = root / ".github" / "workflows" / name
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(textwrap.dedent(body))
    return wf


def _write_pkg(root: Path, scripts: dict[str, str]) -> Path:
    pkg = root / "apps" / "web" / "package.json"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text(json.dumps({"name": "@atr/web", "scripts": scripts}))
    return pkg


# -- Regex unit tests -----------------------------------------------------


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


# -- Workflow file scans --------------------------------------------------


class TestWorkflowScans:
    def test_clean_workflow_passes(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e
            """,
        )
        assert scope.scan(tmp_path) == []

    def test_workflow_run_update_snapshots_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- --update-snapshots
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-contains-forbidden-flag" in v.reason for v in violations)

    def test_workflow_run_short_u_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- -u
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-contains-forbidden-flag" in v.reason for v in violations)

    def test_workflow_run_ignore_snapshots_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- --ignore-snapshots
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-contains-forbidden-flag" in v.reason for v in violations)

    def test_new_evil_workflow_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """A brand-new workflow that invokes Playwright directly is caught."""
        _write_workflow(
            tmp_path,
            "evil.yml",
            """\
            name: Evil
            on: workflow_dispatch
            jobs:
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm exec playwright test -u
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-contains-forbidden-flag" in v.reason for v in violations)
        assert any(v.path.endswith("evil.yml") for v in violations)

    def test_npx_playwright_update_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "other.yml",
            """\
            name: Other
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: npx playwright test --update-snapshots
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, "should detect --update-snapshots in any workflow"

    def test_env_var_with_flag_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "envvar.yml",
            """\
            name: EnvVar
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                env:
                  UPDATE_FLAG: --update-snapshots
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- "$UPDATE_FLAG"
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, "env: value containing the flag must be blocked"

    def test_composite_action_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """`.github/actions/*/action.yml` is also scanned."""
        action = tmp_path / ".github" / "actions" / "runpw" / "action.yml"
        action.parent.mkdir(parents=True, exist_ok=True)
        action.write_text(
            textwrap.dedent(
                """\
                name: Run Playwright
                runs:
                  using: composite
                  steps:
                    - run: playwright test --update-snapshots
                      shell: bash
                """
            )
        )
        violations = scope.scan(tmp_path)
        assert any("workflow-contains-forbidden-flag" in v.reason for v in violations)

    def test_quoted_wrapper_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "bashc.yml",
            """\
            name: BashC
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: bash -c 'playwright test --update-snapshots'
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations

    def test_allow_marker_exempts_line(self, scope: ModuleType, tmp_path: Path) -> None:
        """Lines bearing the ALLOW_MARKER are explicitly exempt."""
        _write_workflow(
            tmp_path,
            "documented.yml",
            """\
            name: Documented
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  # Describing --update-snapshots here is fine.  # visual-gate-scope: allow
                  - run: echo hello
            """,
        )
        assert scope.scan(tmp_path) == []


# -- package.json scans ---------------------------------------------------


class TestPackageJsonScans:
    def test_clean_scripts_pass(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        assert scope.scan(tmp_path) == []

    def test_test_e2e_with_flag_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test --update-snapshots"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_test_e2e_short_u_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_test_e2e_ignore_snapshots_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test --ignore-snapshots"})
        violations = scope.scan(tmp_path)
        assert any(v.reason == "test-e2e-contains-forbidden-flag" for v in violations)

    def test_visual_update_script_alone_is_allowed(self, scope: ModuleType, tmp_path: Path) -> None:
        """A local-only update script is allowed to *exist* in package.json."""
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        assert scope.scan(tmp_path) == []


# -- Cross-file: workflow invoking a tainted script -----------------------


class TestWorkflowScriptRefs:
    def test_workflow_invoking_test_visual_update_blocked(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        _write_workflow(
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
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
                "lint": "oxlint .",
            },
        )
        _write_workflow(
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


# -- CLI ------------------------------------------------------------------


class TestCLI:
    def test_main_exits_zero_on_clean(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e
            """,
        )
        assert scope.main(["--repo-root", str(tmp_path)]) == 0

    def test_main_exits_one_on_violation(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_real_repo_is_clean(self, scope: ModuleType) -> None:
        """The actual repository must pass the scanner."""
        assert scope.main(["--repo-root", str(REPO)]) == 0


# -- Adversarial vector mapping (S5U-608) ---------------------------------


class TestS5U608BypassVectors:
    """Each bypass vector listed in S5U-608 must now fail closed.

    The issue enumerated four concrete bypasses that passed the original
    guard. Every one of them must be caught here. When this test class is
    green, all four vectors are provably blocked.
    """

    def test_vector_1_short_flag_in_package_json(self, scope: ModuleType, tmp_path: Path) -> None:
        # "playwright test -u" inside scripts.test:e2e
        _write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_2_ignore_snapshots_in_package_json(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test --ignore-snapshots"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3_workflow_level_short_flag(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- -u
            """,
        )
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3b_workflow_level_long_flag(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- --update-snapshots
            """,
        )
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3c_workflow_level_ignore(self, scope: ModuleType, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- --ignore-snapshots
            """,
        )
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_4_new_workflow_bypasses_visual_regression_yml(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """A new workflow file never touching visual-regression.yml."""
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        # The canonical visual-regression.yml is untouched and clean:
        _write_workflow(
            tmp_path,
            "visual-regression.yml",
            """\
            name: Visual
            on: workflow_call
            jobs:
              visual:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e
            """,
        )
        # Evil sibling workflow slides in:
        _write_workflow(
            tmp_path,
            "sneak.yml",
            """\
            name: Sneak
            on: push
            jobs:
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm exec playwright test --update-snapshots
            """,
        )
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

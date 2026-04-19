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

    def test_allow_marker_rejected_in_workflow(self, scope: ModuleType, tmp_path: Path) -> None:
        """Post S5U-611: the ALLOW_MARKER is never valid inside `.github/**` YAML.

        The marker was previously an unrestricted single-PR escape hatch. Now
        it must be rejected with a dedicated `allow-marker-not-permitted`
        violation regardless of whether the underlying line contains a
        forbidden flag, because its legitimate use is confined to the
        scanner/guard script sources which are never scanned.
        """
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
        violations = scope.scan(tmp_path)
        assert any(v.reason == "allow-marker-not-permitted" for v in violations), (
            f"expected allow-marker-not-permitted, got {[v.reason for v in violations]}"
        )


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


# -- S5U-611 bypass closures ---------------------------------------------


class TestS5U611AllowMarkerPathAllowlist:
    """Gap 2: ALLOW_MARKER in workflow YAML is an unrestricted bypass.

    Post S5U-611 the marker is never honoured inside `.github/**` YAML; it
    produces a dedicated `allow-marker-not-permitted` violation. Legitimate
    references to the marker literal live only in scanner/guard source
    files (Python/bash), which the scanner does not walk.
    """

    def test_marker_with_update_flag_is_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """Gap 2 repro: the exact `run:` line from the Linear issue."""
        _write_workflow(
            tmp_path,
            "sneaky.yml",
            """\
            name: Sneaky
            on: push
            jobs:
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:e2e -- -u  # visual-gate-scope: allow
            """,
        )
        violations = scope.scan(tmp_path)
        # The forbidden-flag scan must NOT be silenced by the marker.
        assert any(v.reason == "workflow-contains-forbidden-flag" for v in violations)
        # And the marker itself produces its own violation.
        assert any(v.reason == "allow-marker-not-permitted" for v in violations)

    def test_marker_on_benign_line_is_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """The marker is flagged even on lines that carry no forbidden flag.

        The policy is: the marker has no legitimate use in workflow YAML at
        all. Accepting it on benign lines would invite the adversary to
        plant the marker pre-emptively and then reintroduce the flag in a
        later commit under the cover of a passing scanner.
        """
        _write_workflow(
            tmp_path,
            "benign-marker.yml",
            """\
            name: Marker
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hello  # visual-gate-scope: allow
            """,
        )
        violations = scope.scan(tmp_path)
        assert any(v.reason == "allow-marker-not-permitted" for v in violations)

    def test_marker_with_local_only_script_is_blocked(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """Marker does not exempt a local-only-script reference either."""
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
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web run test:visual:update  # visual-gate-scope: allow
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("local-only" in v.reason or "local_only" in v.reason for v in violations)
        assert any(v.reason == "allow-marker-not-permitted" for v in violations)


class TestS5U611BarePnpmShortcut:
    """Gap 3: `pnpm <script>` (bare) bypasses the canonical-form regex.

    Post S5U-611 any workflow line that names a `LOCAL_ONLY_SCRIPTS` entry
    as a word-bounded token is a violation, independent of whether the
    surrounding tokens match `(pnpm|npm|yarn) (run|run-script) <name>`.
    """

    def test_bare_filter_shortcut_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """Gap 3 repro A: `pnpm --filter @atr/web test:visual:update`."""
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
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web test:visual:update
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, "bare pnpm --filter <script> shortcut must be blocked"
        assert any("local-only" in v.reason or "local_only" in v.reason for v in violations), (
            f"expected a local-only violation, got {[v.reason for v in violations]}"
        )

    def test_bare_shortcut_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """Gap 3 repro B: bare `pnpm test:visual:update`."""
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
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm test:visual:update
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, "bare `pnpm <script>` shortcut must be blocked"

    def test_local_only_name_appears_without_invoker(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """Even without a package-manager prefix, naming the script in a
        workflow line is suspicious enough to block. Policy is strict:
        the name should not appear at all in `.github/**` YAML.
        """
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
              bad:
                runs-on: ubuntu-latest
                steps:
                  - run: bash -c "cd apps/web && npm_config_foo=1 pnpm test:visual:update"
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations

    def test_unrelated_exec_still_passes(self, scope: ModuleType, tmp_path: Path) -> None:
        """`pnpm exec playwright test` has no script name and is clean."""
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "install.yml",
            """\
            name: Install
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm install
                  - run: pnpm exec playwright install --with-deps chromium
            """,
        )
        assert scope.scan(tmp_path) == []

    def test_similar_but_distinct_script_name_not_flagged(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """Word-boundary match: `test-visual-update-lib` (dashes, not colons)
        must NOT be flagged. The token we block is exactly
        `test:visual:update`.
        """
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "lib.yml",
            """\
            name: Lib
            on: push
            jobs:
              foo:
                runs-on: ubuntu-latest
                steps:
                  - run: npm install --save test-visual-update-lib
            """,
        )
        assert scope.scan(tmp_path) == []

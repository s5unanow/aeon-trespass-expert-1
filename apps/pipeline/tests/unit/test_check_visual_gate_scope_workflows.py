"""Workflow YAML scan tests for `scripts/check_visual_gate_scope.py` (S5U-608).

S5U-655 split: extracted from the original 902-line file.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import ModuleType

# `scope` fixture is auto-discovered from `tests/unit/conftest.py` (S5U-655).


def write_workflow(root: Path, name: str, body: str) -> Path:
    wf = root / ".github" / "workflows" / name
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(textwrap.dedent(body))
    return wf


class TestWorkflowScans:
    def test_clean_workflow_passes(self, scope: ModuleType, tmp_path: Path) -> None:
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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
        write_workflow(
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

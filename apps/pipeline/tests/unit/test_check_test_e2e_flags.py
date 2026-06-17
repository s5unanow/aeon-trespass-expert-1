"""Tests for scripts/check_test_e2e_flags.sh (S5U-687).

The fallback shell guard runs inside the required `visual-regression / visual`
job. S5U-611 Gap 1 gave it coverage of inline Playwright flags in workflow
YAML; S5U-687 extends it to match the Python scanner's surface (workflow
invocations of local-only/tainted package.json scripts, ALLOW_MARKER presence,
and package.json introducing a new tainted script).

Each test writes a synthetic repo tree under `tmp_path` (package.json +
workflow YAML) and runs the real shell script with `REPO_ROOT=<tmp_path>`.
Tests assert the exit code — 0 for clean inputs, 1 for every bypass vector
the canonical Python scanner catches.

Red-before anchor: `test_workflow_invoking_canonical_local_only_blocked`
fails against the pre-S5U-687 script (which only checked inline flag tokens,
never script-name references). See the PR body's `Red-before confirmation:`
for the exact failure excerpt.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_test_e2e_flags.sh"

_PATH_ENV = os.environ.get("PATH", "/usr/bin:/bin")

# The canonical shape of `apps/web/package.json` scripts under test: the
# sanctioned local-only updater coexisting with a clean `test:e2e`. Shared
# by every test that invokes the local-only script from a workflow.
_PKG_WITH_LOCAL_ONLY: dict[str, str] = {
    "test:e2e": "playwright test",
    "test:visual:update": "playwright test --update-snapshots",
}


def _write_pkg(root: Path, scripts: dict[str, str]) -> Path:
    pkg = root / "apps" / "web" / "package.json"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text(json.dumps({"name": "@atr/web", "scripts": scripts}))
    return pkg


def _write_workflow(root: Path, name: str, body: str) -> Path:
    wf = root / ".github" / "workflows" / name
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(textwrap.dedent(body))
    return wf


def _write_action(root: Path, action_name: str, body: str) -> Path:
    action = root / ".github" / "actions" / action_name / "action.yml"
    action.parent.mkdir(parents=True, exist_ok=True)
    action.write_text(textwrap.dedent(body))
    return action


def _run(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env={"REPO_ROOT": str(tmp_path), "PATH": _PATH_ENV},
        capture_output=True,
        text=True,
        check=False,
    )


def _wf_one_step(run_line: str) -> str:
    """Build a minimal workflow YAML body with a single `run:` step."""
    return textwrap.dedent(
        f"""\
        name: X
        on: push
        jobs:
          j:
            runs-on: ubuntu-latest
            steps:
              - run: {run_line}
        """
    )


# -- Happy path -----------------------------------------------------------


def test_clean_repo_passes(tmp_path: Path) -> None:
    _write_pkg(
        tmp_path,
        {
            "test:e2e": "playwright test",
            "test:visual:update": "playwright test --update-snapshots",
        },
    )
    _write_workflow(tmp_path, "v.yml", _wf_one_step("pnpm --filter @atr/web run test:e2e"))
    result = _run(tmp_path)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


@pytest.mark.slow  # S5U-1230: full-pipeline-chain; excluded from fast pre-commit subset
def test_real_repo_is_clean() -> None:
    """The actual repository must pass the fallback guard."""
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env={"REPO_ROOT": str(REPO), "PATH": _PATH_ENV},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


# -- test:e2e body scan (existing behavior; regression pins) --------------


@pytest.mark.parametrize(
    "body",
    [
        "playwright test -u",
        "playwright test --update-snapshots",
        "playwright test --ignore-snapshots",
        "playwright test --update-snapshots=true",
    ],
    ids=["short-u", "long-update", "ignore-snapshots", "equals-form"],
)
def test_test_e2e_body_with_forbidden_flag_blocked(tmp_path: Path, body: str) -> None:
    _write_pkg(tmp_path, {"test:e2e": body})
    assert _run(tmp_path).returncode == 1


# -- Inline workflow flag scan (existing S5U-611 Gap 1 pins) --------------


@pytest.mark.parametrize(
    "run_line",
    [
        "pnpm --filter @atr/web run test:e2e -- --update-snapshots",
        "pnpm --filter @atr/web run test:e2e -- -u",
        "pnpm --filter @atr/web run test:e2e -- --ignore-snapshots",
    ],
    ids=["long-update", "short-u", "ignore-snapshots"],
)
def test_workflow_inline_flag_blocked(tmp_path: Path, run_line: str) -> None:
    _write_pkg(tmp_path, {"test:e2e": "playwright test"})
    _write_workflow(tmp_path, "v.yml", _wf_one_step(run_line))
    assert _run(tmp_path).returncode == 1


def test_composite_action_flag_blocked(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"test:e2e": "playwright test"})
    _write_action(
        tmp_path,
        "runpw",
        """\
        name: Run Playwright
        runs:
          using: composite
          steps:
            - run: playwright test --update-snapshots
              shell: bash
        """,
    )
    assert _run(tmp_path).returncode == 1


# -- S5U-687 NEW: workflow invokes local-only / tainted scripts -----------


class TestWorkflowInvokesLocalOnlyScript:
    """Primary S5U-687 surface: workflow invocations of local-only updaters.

    The pre-S5U-687 shell guard only inspected inline flag tokens in workflow
    `run:` lines. A workflow that invoked the intentional local-only script
    (`pnpm --filter @atr/web run test:visual:update`) bypassed the fallback
    entirely, because the script name carries no forbidden flag token.
    """

    def test_workflow_invoking_canonical_local_only_blocked(self, tmp_path: Path) -> None:
        """Red-before anchor: canonical `pnpm --filter run test:visual:update`."""
        _write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        _write_workflow(
            tmp_path,
            "sneaky.yml",
            _wf_one_step("pnpm --filter @atr/web run test:visual:update"),
        )
        result = _run(tmp_path)
        assert result.returncode == 1, (
            f"expected blocked canonical local-only invocation; "
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

    def test_workflow_invoking_bare_local_only_blocked(self, tmp_path: Path) -> None:
        """Bare pnpm shortcut: `pnpm test:visual:update`."""
        _write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        _write_workflow(tmp_path, "sneaky.yml", _wf_one_step("pnpm test:visual:update"))
        assert _run(tmp_path).returncode == 1

    def test_workflow_invoking_bare_filter_local_only_blocked(self, tmp_path: Path) -> None:
        """Bare pnpm --filter shortcut: `pnpm --filter @atr/web test:visual:update`."""
        _write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        _write_workflow(
            tmp_path,
            "sneaky.yml",
            _wf_one_step("pnpm --filter @atr/web test:visual:update"),
        )
        assert _run(tmp_path).returncode == 1


# -- S5U-687 NEW: rename + tainted-script closure (G2) --------------------


class TestRenameAndTaintedScriptClosure:
    """G2 content-derived coverage: the blocked set is derived from scripts'
    bodies, not a hardcoded name list. Any renamed script whose body carries
    a forbidden flag is treated as tainted and its workflow invocations
    are blocked."""

    def test_workflow_invoking_renamed_tainted_script_blocked(self, tmp_path: Path) -> None:
        """Rename of `test:visual:update` to `test:visual-update` (hyphen)."""
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        _write_workflow(tmp_path, "rename.yml", _wf_one_step("pnpm test:visual-update"))
        assert _run(tmp_path).returncode == 1

    def test_workflow_invoking_arbitrary_tainted_rename_blocked(self, tmp_path: Path) -> None:
        """Arbitrary new name `refresh-snapshots` with forbidden flag in body."""
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "refresh-snapshots": "playwright test --update-snapshots",
            },
        )
        _write_workflow(tmp_path, "refresh.yml", _wf_one_step("pnpm refresh-snapshots"))
        assert _run(tmp_path).returncode == 1

    def test_package_json_introduces_tainted_script_fails_alone(self, tmp_path: Path) -> None:
        """Introducing a non-allowlisted tainted script fails by itself.

        No workflow invocation required. The package.json diff alone is a
        reviewer-visible violation.
        """
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        assert _run(tmp_path).returncode == 1

    def test_rename_filter_bare_shortcut_blocked(self, tmp_path: Path) -> None:
        """`pnpm --filter @atr/web test:visual-update` — rename + bare filter."""
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        _write_workflow(
            tmp_path,
            "filter-rename.yml",
            _wf_one_step("pnpm --filter @atr/web test:visual-update"),
        )
        assert _run(tmp_path).returncode == 1


# -- S5U-687 NEW: ALLOW_MARKER presence in workflow YAML ------------------


class TestAllowMarkerInWorkflow:
    """The legacy `# visual-gate-scope: allow` marker has no legitimate use
    inside `.github/**` YAML (S5U-611 Gap 2). The fallback now enforces this
    too: the marker's presence on any workflow/action line fails the guard,
    independent of any forbidden flag on the same line."""

    def test_allow_marker_on_benign_line_blocked(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "benign-marker.yml",
            _wf_one_step("echo hello  # visual-gate-scope: allow"),
        )
        assert _run(tmp_path).returncode == 1

    def test_allow_marker_with_flag_blocked(self, tmp_path: Path) -> None:
        """Marker does not silence the forbidden-flag check."""
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "sneaky.yml",
            _wf_one_step("pnpm --filter @atr/web run test:e2e -- -u  # visual-gate-scope: allow"),
        )
        assert _run(tmp_path).returncode == 1


# -- S5U-687 NEW: false-positive guards -----------------------------------


class TestFalsePositiveGuards:
    def test_similar_but_distinct_script_name_passes(self, tmp_path: Path) -> None:
        """`test-visual-update-lib` (dashes, not colons) must not be flagged.

        The blocked token is exactly `test:visual:update` with colons.
        """
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(
            tmp_path,
            "lib.yml",
            _wf_one_step("npm install --save test-visual-update-lib"),
        )
        result = _run(tmp_path)
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    def test_clean_rename_without_flag_passes(self, tmp_path: Path) -> None:
        """A renamed name whose body is clean must not be treated as tainted."""
        _write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test",  # clean body
            },
        )
        _write_workflow(tmp_path, "clean.yml", _wf_one_step("pnpm test:visual-update"))
        result = _run(tmp_path)
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    def test_unrelated_workflow_scripts_pass(self, tmp_path: Path) -> None:
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
            textwrap.dedent(
                """\
                name: OK
                on: push
                jobs:
                  j:
                    runs-on: ubuntu-latest
                    steps:
                      - run: pnpm -r run lint
                      - run: pnpm --filter @atr/web run test:e2e
                """
            ),
        )
        result = _run(tmp_path)
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


# -- S5U-687 NEW: G1 degenerate-input fail-closed coverage ----------------


class TestDegenerateInputs:
    def test_package_json_missing_fails_closed(self, tmp_path: Path) -> None:
        """apps/web/package.json absent → guard exits non-zero."""
        # No package.json written.
        assert _run(tmp_path).returncode == 1

    def test_package_json_malformed_fails_closed(self, tmp_path: Path) -> None:
        """Garbage JSON in apps/web/package.json → guard exits non-zero.

        `node -e` throws on parse error; `set -euo pipefail` propagates.
        """
        pkg = tmp_path / "apps" / "web" / "package.json"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_text("{ not valid json at all")
        assert _run(tmp_path).returncode != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

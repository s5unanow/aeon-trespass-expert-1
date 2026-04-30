"""S5U-611 closure tests for `check_visual_gate_scope.py`.

S5U-655 split: extracted from the original 902-line file. Covers
ALLOW_MARKER path allowlist (Gap 2) and bare-pnpm shortcut (Gap 3).
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


class TestS5U611AllowMarkerPathAllowlist:
    """Gap 2: ALLOW_MARKER in workflow YAML is an unrestricted bypass.

    Post S5U-611 the marker is never honoured inside `.github/**` YAML; it
    produces a dedicated `allow-marker-not-permitted` violation. Legitimate
    references to the marker literal live only in scanner/guard source
    files (Python/bash), which the scanner does not walk.
    """

    def test_marker_with_update_flag_is_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """Gap 2 repro: the exact `run:` line from the Linear issue."""
        write_workflow(
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
        write_workflow(
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
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
        write_workflow(
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
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
        write_workflow(
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

"""S5U-637 closure tests + S5U-655 local-only-script terminator coverage.

S5U-655 split: extracted from the original 902-line file. Adds shell-
terminator coverage for the local-only-script matcher
(`_local_only_token_patterns`) — the issue's worked examples
(`pnpm test:visual:update;`, `bash -c "pnpm test:visual:update; echo ok"`,
etc.) bypass the pre-S5U-655 narrow trailing class.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

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


class TestS5U637RenameAndBareShortcut:
    """S5U-611 closed the bare-shortcut surface for the hardcoded local-only
    name `test:visual:update`. But an attacker who controls `package.json`
    can rename that script (e.g. to `test:visual-update` with a hyphen) and
    invoke it via the pnpm bare shortcut (`pnpm test:visual-update`). The
    S5U-611 implementation only matched word-bounded tokens from the
    hardcoded `LOCAL_ONLY_SCRIPTS` set, not the dynamic `tainted` set, so
    the rename escaped both layers of the workflow-scan.

    S5U-637 feeds `tainted` into the token-pattern layer (primary fix) and
    additionally emits a `package-json-introduces-tainted-script` violation
    for any script outside `{test:e2e, test:visual:update}` that carries a
    forbidden flag (secondary fix), turning the rename into a reviewer-
    visible package-json diff failure.
    """

    def test_renamed_script_bare_pnpm_is_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """Exact repro from the Linear issue: rename + bare pnpm shortcut.

        This is the red-before anchor for the primary fix. It must fail
        against the pre-S5U-637 scanner and pass after.
        """
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        write_workflow(
            tmp_path,
            "rename.yml",
            """\
            name: Rename
            on: push
            jobs:
              j:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm test:visual-update
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, (
            f"rename + bare-pnpm bypass must be blocked; got {[v.reason for v in violations]}"
        )

    def test_renamed_script_with_filter_bare_shortcut_is_blocked(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """`pnpm --filter @atr/web test:visual-update` (bare + filter, rename)."""
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        write_workflow(
            tmp_path,
            "filter-rename.yml",
            """\
            name: FilterRename
            on: push
            jobs:
              j:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm --filter @atr/web test:visual-update
            """,
        )
        violations = scope.scan(tmp_path)
        assert violations, (
            f"bare filter + renamed shortcut must be blocked; got {[v.reason for v in violations]}"
        )

    def test_arbitrary_renamed_name_also_blocked(self, scope: ModuleType, tmp_path: Path) -> None:
        """A totally different name (`refresh-snapshots`) must also be blocked.

        A substring-based heuristic on `test:visual*` would miss this; only
        a dynamic-tainted-set closure catches it.
        """
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "refresh-snapshots": "playwright test --update-snapshots",
            },
        )
        write_workflow(
            tmp_path,
            "refresh.yml",
            """\
            name: Refresh
            on: push
            jobs:
              j:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm refresh-snapshots
            """,
        )
        violations = scope.scan(tmp_path)
        assert any("tainted" in v.reason or "local-only" in v.reason for v in violations), (
            f"tainted rename must be blocked; got {[v.reason for v in violations]}"
        )

    def test_package_json_introduces_tainted_script_violation(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """Secondary fix: a new tainted script name in package.json fails by itself.

        Even without any workflow invocation, introducing a new script
        outside the `{test:e2e, test:visual:update}` allowlist that carries
        a forbidden flag is a scanner violation.
        """
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test --update-snapshots",
            },
        )
        violations = scope.scan(tmp_path)
        assert any(
            v.reason.startswith("package-json-introduces-tainted-script") for v in violations
        ), (
            "package.json introducing a non-allowlisted tainted script must be blocked; "
            f"got {[v.reason for v in violations]}"
        )

    def test_allowed_local_only_script_still_passes(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """Regression pin: the sanctioned `test:visual:update` still passes."""
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual:update": "playwright test --update-snapshots",
            },
        )
        # No workflow invocation.
        assert scope.scan(tmp_path) == []

    def test_similar_non_tainted_name_not_flagged(self, scope: ModuleType, tmp_path: Path) -> None:
        """False-positive guard: a renamed-style name without the flag is fine.

        `test:visual-update` whose body is clean (no `--update-snapshots`)
        is neither tainted nor introduces a violation. The secondary fix
        must not sweep up clean scripts.
        """
        write_pkg(
            tmp_path,
            {
                "test:e2e": "playwright test",
                "test:visual-update": "playwright test",  # clean body
            },
        )
        write_workflow(
            tmp_path,
            "clean.yml",
            """\
            name: Clean
            on: push
            jobs:
              j:
                runs-on: ubuntu-latest
                steps:
                  - run: pnpm test:visual-update
            """,
        )
        assert scope.scan(tmp_path) == []


# -- S5U-655: local-only-script shell-terminator coverage -----------------
#
# The pre-S5U-655 trailing class for the local-only-script matcher
# (`_local_only_token_patterns`) was `[\\s"'`]|$` — too narrow. Real shell
# vectors using `;`, `&`, `|`, `)`, `(`, `<`, `>`, `,` after the script
# name bypassed the matcher. Each terminator gets a happy-path (BLOCK)
# below; false-positive guards live in `TestS5U611BarePnpmShortcut`
# (which already covers `test-visual-update-lib`, dashes, etc.).


_PKG_WITH_LOCAL_ONLY: dict[str, str] = {
    "test:e2e": "playwright test",
    "test:visual:update": "playwright test --update-snapshots",
}


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


class TestLocalOnlyShellTerminator:
    """Local-only-script matcher must catch every shell-terminator variant.

    Each input has the script name immediately followed by the new
    terminator (no intervening whitespace) so the test exercises the
    new char-class additions specifically.
    """

    @pytest.mark.parametrize(
        "run_line",
        [
            # `;` — issue worked example, no whitespace before terminator
            "pnpm test:visual:update;",
            # `;` inside quoted bash -c body — issue worked example
            'bash -c "pnpm test:visual:update; echo ok"',
            # `|` — pipe immediately after the script name
            "pnpm test:visual:update|tee log",
            # `)` — close of a wrapping subshell, no leading whitespace
            "(pnpm test:visual:update)",
            # `&` — chained command immediately after script name
            "pnpm test:visual:update&& echo ok",
            # `,` — comma-list of script names
            "pnpm test:visual:update,test:e2e",
            # `<` — input redirect immediately after script name
            "pnpm test:visual:update<input.txt",
            # `>` — output redirect immediately after script name
            "pnpm test:visual:update>log.txt",
        ],
        ids=[
            "semicolon",
            "quoted-semicolon",
            "pipe",
            "rparen",
            "amp",
            "comma",
            "lt-redir",
            "gt-redir",
        ],
    )
    def test_local_only_with_shell_terminator_blocked(
        self, scope: ModuleType, tmp_path: Path, run_line: str
    ) -> None:
        write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        write_workflow(tmp_path, "sneaky.yml", _wf_one_step(run_line))
        violations = scope.scan(tmp_path)
        assert violations, (
            f"local-only script with shell terminator must be blocked; "
            f"got {[v.reason for v in violations]} for run_line={run_line!r}"
        )

    def test_dash_substring_still_clean(self, scope: ModuleType, tmp_path: Path) -> None:
        """False-positive regression pin: dashes in `test-visual-update-lib`."""
        write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        write_workflow(
            tmp_path,
            "lib.yml",
            _wf_one_step("npm install --save test-visual-update-lib"),
        )
        # No `test:visual:update` token (dashes vs colons).
        assert scope.scan(tmp_path) == []

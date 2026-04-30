"""Shell-terminator tests for `scripts/check_test_e2e_flags.sh` (S5U-655).

Mirror of the Python scanner's terminator coverage in
`test_check_visual_gate_scope_regex.py` and
`test_check_visual_gate_scope_s5u637.py`. Pre-S5U-655 the shell pattern's
leading/trailing classes were `[[:space:]"'`]` / `[[:space:]="'`]`. Real
shell vectors using punctuation terminators (`;`, `&`, `|`, `(`, `)`,
`<`, `>`, `,`) bypassed both the inline forbidden-flag scan and the
local-only-script scan. S5U-655 broadens both classes; these tests pin
the closure.

Red-before anchor: ran the new tests against commit `823ae47cc261eb5c962e0ef2f55f338a3c9c7780`
(the S5U-655 split commit, paired with this commit) with the shell
script `pattern` regex temporarily reverted to its pre-S5U-655 form;
all 16 tests below failed with `assert result.returncode == 1` (actual
returncode 0). Re-applied the broadened regex and the same 16 tests
pass.
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


def _run(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env={"REPO_ROOT": str(tmp_path), "PATH": _PATH_ENV},
        capture_output=True,
        text=True,
        check=False,
    )


def _wf_one_step(run_line: str) -> str:
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


class TestShellTerminatorInlineFlag:
    """Inline forbidden-flag matcher: each terminator must BLOCK.

    Each input has the forbidden flag immediately followed by the new
    terminator (no intervening whitespace) so the test exercises the
    new char-class additions specifically; whitespace alone already
    matched pre-S5U-655.
    """

    @pytest.mark.parametrize(
        "run_line",
        [
            # `;` — issue worked example
            "pnpm exec playwright test -u; echo ok",
            # `&` — `&&` chain immediately after the flag
            "playwright test --update-snapshots&& echo ok",
            # `|` — pipe immediately after the flag
            "pnpm exec playwright test -u|tee log",
            # `)` — issue worked example, subshell close
            "playwright test --ignore-snapshots)",
            # `(` — leading paren before the flag (subshell open)
            "(playwright test -u)",
            # `<` — input redirect immediately after the flag
            "playwright test -u<input.txt",
            # `>` — output redirect immediately after the flag
            "playwright test --update-snapshots>out.log",
            # `,` — comma-separated arg list (bash array)
            "args=(--update-snapshots,--reporter=html)",
        ],
        ids=["semicolon", "ampersand", "pipe", "rparen", "lparen", "lt", "gt", "comma"],
    )
    def test_shell_terminator_inline_flag_blocked(self, tmp_path: Path, run_line: str) -> None:
        _write_pkg(tmp_path, {"test:e2e": "playwright test"})
        _write_workflow(tmp_path, "v.yml", _wf_one_step(run_line))
        result = _run(tmp_path)
        assert result.returncode == 1, (
            f"expected blocked; stdout={result.stdout}\nstderr={result.stderr}"
        )


class TestShellTerminatorLocalOnlyScript:
    """Local-only-script matcher: each terminator must BLOCK."""

    @pytest.mark.parametrize(
        "run_line",
        [
            # `;` — issue worked example
            "pnpm test:visual:update;",
            # `;` inside quoted bash -c body — issue worked example
            'bash -c "pnpm test:visual:update; echo ok"',
            # `|` — pipe immediately after the script name
            "pnpm test:visual:update|tee log",
            # `)` — close of a wrapping subshell
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
        ids=["semicolon", "quoted-semi", "pipe", "rparen", "amp", "comma", "lt", "gt"],
    )
    def test_shell_terminator_local_only_blocked(self, tmp_path: Path, run_line: str) -> None:
        _write_pkg(tmp_path, _PKG_WITH_LOCAL_ONLY)
        _write_workflow(tmp_path, "sneaky.yml", _wf_one_step(run_line))
        result = _run(tmp_path)
        assert result.returncode == 1, (
            f"expected blocked; stdout={result.stdout}\nstderr={result.stderr}"
        )

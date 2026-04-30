"""CLI / S5U-608 bypass-vector tests for `check_visual_gate_scope.py`.

S5U-655 split: extracted from the original 902-line file.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from types import ModuleType

# `scope` fixture is auto-discovered from `tests/unit/conftest.py` (S5U-655).

REPO = Path(__file__).resolve().parents[4]


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


class TestCLI:
    def test_main_exits_zero_on_clean(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
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
        assert scope.main(["--repo-root", str(tmp_path)]) == 0

    def test_main_exits_one_on_violation(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_real_repo_is_clean(self, scope: ModuleType) -> None:
        """The actual repository must pass the scanner."""
        assert scope.main(["--repo-root", str(REPO)]) == 0


class TestS5U608BypassVectors:
    """Each bypass vector listed in S5U-608 must now fail closed.

    The issue enumerated four concrete bypasses that passed the original
    guard. Every one of them must be caught here. When this test class is
    green, all four vectors are provably blocked.
    """

    def test_vector_1_short_flag_in_package_json(self, scope: ModuleType, tmp_path: Path) -> None:
        # "playwright test -u" inside scripts.test:e2e
        write_pkg(tmp_path, {"test:e2e": "playwright test -u"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_2_ignore_snapshots_in_package_json(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test --ignore-snapshots"})
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3_workflow_level_short_flag(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
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
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3b_workflow_level_long_flag(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
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
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_3c_workflow_level_ignore(self, scope: ModuleType, tmp_path: Path) -> None:
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
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
        assert scope.main(["--repo-root", str(tmp_path)]) == 1

    def test_vector_4_new_workflow_bypasses_visual_regression_yml(
        self, scope: ModuleType, tmp_path: Path
    ) -> None:
        """A new workflow file never touching visual-regression.yml."""
        write_pkg(tmp_path, {"test:e2e": "playwright test"})
        # The canonical visual-regression.yml is untouched and clean:
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
        # Evil sibling workflow slides in:
        write_workflow(
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

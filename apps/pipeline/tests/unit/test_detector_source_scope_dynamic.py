"""S5U-996: import-graph scope for dotted + dynamic sibling imports.

S5U-926's ``import_graph_scope()`` AST walk in ``scripts/_detector_source_scope.py``
was sound for the bare ``from _x import …`` style every live detector uses, but
had two under-capture blind spots in the dangerous direction:

1. **Dotted package imports** — ``from scripts._helper import f`` /
   ``import scripts._helper`` kept only the first dotted component (``scripts``),
   which resolved to no ``scripts/scripts.py`` file, so ``_helper`` escaped scope.
2. **Dynamic imports** — ``importlib.import_module("_helper")`` /
   ``__import__("_helper")`` carry no ``ast.Import`` / ``ast.ImportFrom`` edge, so
   the helper was invisible.

Both re-opened the exact bypass S5U-926 closes (a lone edit to a load-bearing
helper escapes the coordinator-ack pre-PR refusal + post-merge audit) for a
future detector adopting either style. This module pins the fix and its
over-capture / fail-closed guards.

These tests live in a separate module from ``test_detector_source_scope.py`` to
keep both files under the 400-line source-length limit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "_detector_source_scope.py"


def _load() -> ModuleType:
    if str(REPO / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("_detector_source_scope", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_script(scripts_dir: Path, name: str, body: str) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / name).write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Dotted package-style sibling imports
# ---------------------------------------------------------------------------


def test_import_graph_captures_dotted_from_scripts_helper(tmp_path: Path) -> None:
    """`from scripts._helper import f` resolves _helper (was OUT pre-fix)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from scripts._real_helper import f\n")
    _write_script(scripts, "_real_helper.py", "def f() -> None: ...\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_real_helper.py"})


def test_import_graph_captures_dotted_import_scripts_helper(tmp_path: Path) -> None:
    """`import scripts._helper` resolves _helper (was OUT pre-fix)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "import scripts._real_helper\n")
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_real_helper.py"})


def test_import_graph_dotted_non_scripts_package_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: only the `scripts` package gets the 2nd-component rule.

    `from foo._bar import x` yields only `foo`; there is no scripts/foo.py and
    `_bar` is NOT yielded, so the existing scripts/_bar.py is not captured.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from foo._bar import x\n")
    _write_script(scripts, "_bar.py", "X = 1\n")  # exists but must NOT be captured
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_dotted_missing_helper_is_no_phantom(tmp_path: Path) -> None:
    """Over-capture guard: dotted 2nd-component with no file → no phantom capture."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from scripts._ghost import f\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# Dynamic (importlib / __import__) sibling imports
# ---------------------------------------------------------------------------


def test_import_graph_captures_dynamic_import_module_literal(tmp_path: Path) -> None:
    """importlib.import_module("_helper") string literal is captured."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_import_graph_captures_bare_import_module_literal(tmp_path: Path) -> None:
    """Aliased `from importlib import import_module` bare call is captured."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from importlib import import_module\n_h = import_module('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_import_graph_captures_dunder_import_literal(tmp_path: Path) -> None:
    """__import__("_helper") string literal is captured."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "_h = __import__('_dyn_helper')\n")
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_import_graph_captures_keyword_name_literal(tmp_path: Path) -> None:
    """import_module(name="_helper") keyword form is captured like the positional."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module(name='_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_import_graph_dynamic_keyword_variable_fails_closed(tmp_path: Path) -> None:
    """G1: a non-constant keyword module name fails closed (no keyword escape)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\nn = '_h'\n_x = importlib.import_module(name=n)\n",
    )
    with pytest.raises(mod.DetectorScopeError, match="non-constant module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_dynamic_non_underscore_literal_ignored(tmp_path: Path) -> None:
    """import_module("pydantic") (non-`_` literal) is ignored, not failed-closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_p = importlib.import_module('pydantic')\n",
    )
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_dynamic_variable_arg_fails_closed(tmp_path: Path) -> None:
    """G1: a non-constant (variable) dynamic module name fails closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\nname = '_dyn_helper'\n_h = importlib.import_module(name)\n",
    )
    with pytest.raises(mod.DetectorScopeError, match="non-constant module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_dynamic_fstring_arg_fails_closed(tmp_path: Path) -> None:
    """G1: an f-string dynamic module name fails closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\nx = 'helper'\n_h = importlib.import_module(f'_{x}')\n",
    )
    with pytest.raises(mod.DetectorScopeError, match="non-constant module name"):
        mod.import_graph_scope(repo_root=tmp_path)

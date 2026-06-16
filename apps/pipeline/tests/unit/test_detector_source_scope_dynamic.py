"""S5U-996: import-graph scope for dotted + dynamic sibling imports.

S5U-926's ``import_graph_scope()`` AST walk in ``scripts/_detector_source_scope.py``
was sound for the bare ``from _x import …`` style every live detector uses, but
had two under-capture blind spots in the dangerous direction:

1. **Dotted package imports** — ``from scripts._helper import f`` /
   ``import scripts._helper`` kept only the first dotted component (``scripts``), so
   ``_helper`` escaped scope.
2. **Dynamic imports** — ``importlib.import_module("_helper")`` /
   ``__import__("_helper")`` carry no ``ast.Import`` / ``ast.ImportFrom`` edge, so the
   helper was invisible.

Both re-opened the exact bypass S5U-926 closes (a lone edit to a load-bearing helper
escapes the coordinator-ack pre-PR refusal + post-merge audit). This module pins the
fix and its over-capture / fail-closed guards. Lives in a separate module from
``test_detector_source_scope.py`` to keep both under the 400-line cap.
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

    `from foo._bar import x` yields only `foo`, so the existing scripts/_bar.py is not captured.
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
    body = "import importlib\nn = '_h'\n_x = importlib.import_module(name=n)\n"
    _write_script(scripts, "check_foo.py", body)
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
    body = "import importlib\nname = '_dyn_helper'\n_h = importlib.import_module(name)\n"
    _write_script(scripts, "check_foo.py", body)
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


# ---------------------------------------------------------------------------
# Dynamic + dotted (S5U-1097): import_module("scripts._helper")
# ---------------------------------------------------------------------------


def test_import_graph_captures_dynamic_dotted_scripts_helper_literal(tmp_path: Path) -> None:
    """S5U-1097: `import_module("scripts._helper")` resolves _helper (was OUT pre-fix).

    The dotted literal does not start with `_`, so the pre-fix `startswith("_")` branch
    silently ignored it. Routing it through `_dotted_candidate_names` yields the
    `scripts`-package second component `_real_helper`.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('scripts._real_helper')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_real_helper.py"})


def test_import_graph_dynamic_dotted_non_scripts_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: dynamic `import_module("foo._bar")` yields only `foo`.

    The `scripts`-package second-component rule keys on the exact first part `scripts`;
    `foo._bar` does not get it, so the existing scripts/_bar.py is NOT captured.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('foo._bar')\n",
    )
    _write_script(scripts, "_bar.py", "X = 1\n")  # exists but must NOT be captured
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_dynamic_dotted_missing_helper_no_phantom(tmp_path: Path) -> None:
    """Phantom guard: dynamic dotted 2nd-component with no file → no capture."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('scripts._ghost')\n",
    )
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# Relative dynamic literal (S5U-1100): import_module("._helper", package="scripts")
# ---------------------------------------------------------------------------


def test_import_graph_captures_relative_dynamic_keyword_package(tmp_path: Path) -> None:
    """S5U-1100: `import_module("._h", package="scripts")` resolves _h (was OUT pre-fix).

    Pre-fix the empty first component of `"._h".split(".")` was dropped by the leading-`_`
    gate — silent escape. The constant `package="scripts"` anchor + dot-strip captures it.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('._real_helper', package='scripts')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_real_helper.py"})


def test_import_graph_captures_relative_dynamic_positional_package(tmp_path: Path) -> None:
    """S5U-1100: `package` as the SECOND POSITIONAL arg (args[1]) is read like the keyword.

    `importlib.import_module(name, package=None)` — package is positional-or-keyword.
    A keyword-only reader would miss `import_module("._h", "scripts")`; reading
    `node.args[1]` closes that.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('._real_helper', 'scripts')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_real_helper.py"})


def test_import_graph_relative_dynamic_no_package_fails_closed(tmp_path: Path) -> None:
    """G1: a relative literal with NO package anchor is irreducible → fail closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('._real_helper')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dynamic_variable_package_fails_closed(tmp_path: Path) -> None:
    """G1: a non-constant `package` anchor is irreducible → fail closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\npkg = 'scripts'\n"
        "_h = importlib.import_module('._real_helper', package=pkg)\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dynamic_other_constant_package_no_over_capture(
    tmp_path: Path,
) -> None:
    """Over-capture guard: `package="foo"` names foo._bar, NOT a scripts sibling.

    A naive "strip dots, route regardless of package" impl would capture the existing
    scripts/_bar.py; the fix fails closed on any constant package other than "scripts".
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('._bar', package='foo')\n",
    )
    _write_script(scripts, "_bar.py", "X = 1\n")  # exists but must NOT be captured
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dunder_import_fails_closed(tmp_path: Path) -> None:
    """G1: `__import__("._h")` (no second arg) has no string `package` anchor → fail closed.

    The builtin uses an integer `level` for relative imports, not a string anchor; a
    leading-dot literal is a runtime error and names no sibling.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "_h = __import__('._real_helper')\n")
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dunder_import_positional_package_fails_closed(
    tmp_path: Path,
) -> None:
    """S5U-1109: `__import__("._h", "scripts")` does NOT misread positional-2 as a package.

    The builtin `__import__(name, globals, ...)` makes positional-2 `globals` (a mapping),
    never a package string. Pre-fix `_package_arg` read `node.args[1]` for ANY recognized
    callable, so `"scripts"` matched `_SCRIPTS_PACKAGE` and `scripts/_real_helper.py` was
    silently captured. The seed-aware resolver honors a `package` anchor only for an
    `import_module`-origin call, so this fails closed.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "_h = __import__('._real_helper', 'scripts')\n")
    _write_script(scripts, "_real_helper.py", "X = 1\n")  # exists but must NOT be captured
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dunder_import_rebind_inherits_seed_fails_closed(
    tmp_path: Path,
) -> None:
    """S5U-1109: a rebound `imp = __import__` call inherits the `__import__` seed.

    `imp = __import__; imp('._h', 'scripts')` must fail closed like the direct form —
    the seed propagates through the fixpoint fold, so `imp` carries the `__import__`
    seed and positional-2 `'scripts'` is NOT a package anchor. Guards a seed-leakage
    bypass where a rebind erases the builtin origin.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "imp = __import__\n_h = imp('._real_helper', 'scripts')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")  # exists but must NOT be captured
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_relative_dynamic_multi_dot_fails_closed(tmp_path: Path) -> None:
    """G1: a multi-level relative literal `".._h"` escapes the flat-sibling model.

    `package="scripts"` + two leading dots resolves above the scripts package → fail closed.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('.._real_helper', package='scripts')\n",
    )
    _write_script(scripts, "_real_helper.py", "X = 1\n")
    with pytest.raises(mod.DetectorScopeError, match="relative module name"):
        mod.import_graph_scope(repo_root=tmp_path)

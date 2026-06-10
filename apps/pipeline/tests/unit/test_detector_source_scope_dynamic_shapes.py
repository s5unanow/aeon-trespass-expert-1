"""S5U-1098: aliased / rebound / **kwargs dynamic-import call shapes.

S5U-996's ``_dynamic_helper_names`` matched dynamic-import calls by callable
*name* only against the frozen set ``{"import_module", "__import__"}``. Three
shapes that ARE ``import_module`` / ``__import__`` semantically escaped the scan
silently (no capture, no fail-closed) — a Rule-G2 name-derived weakness where a
rename / rebind bypasses a content-protecting safety gate:

1. **Aliased import** — ``from importlib import import_module as im`` + ``im(...)``.
2. **Rebound name** — ``imp = __import__`` / ``f = importlib.import_module`` + call.
3. ``**kwargs`` **splat** — ``import_module(**k)`` (statically irreducible, should
   fail closed like the variable-arg case, not fall through silently).

The fix lives in ``scripts/_dynamic_import_scope.py`` (split out of
``_detector_source_scope.py`` to keep both under the 400-line cap; the new module
is brought into safety-gate scope via the import-graph closure — pinned by
``test_dynamic_import_scope_module_is_in_safety_gate_scope`` below).

These tests live in a separate module from ``test_detector_source_scope_dynamic.py``
to keep both files under the 400-line source-length limit.
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
# (1) Aliased import — `from importlib import import_module as im`
# ---------------------------------------------------------------------------


def test_aliased_import_module_call_is_captured(tmp_path: Path) -> None:
    """`from importlib import import_module as im` + `im("_h")` is captured.

    Red-before (45decab): callable name `im` ∉ frozenset → frozenset() (silent escape).
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from importlib import import_module as im\n_h = im('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_aliased_dunder_import_call_is_captured(tmp_path: Path) -> None:
    """`from builtins import __import__ as imp` + `imp("_h")` is captured.

    Red-before (45decab): callable name `imp` ∉ frozenset → frozenset().
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from builtins import __import__ as imp\n_h = imp('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


# ---------------------------------------------------------------------------
# (2) Rebound name — `imp = __import__` / `f = importlib.import_module`
# ---------------------------------------------------------------------------


def test_rebound_dunder_assign_call_is_captured(tmp_path: Path) -> None:
    """`imp = __import__` + `imp("_h")` is captured (Assign rebind).

    Red-before (45decab): name `imp` ∉ frozenset → frozenset().
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "imp = __import__\n_h = imp('_dyn_helper')\n")
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_rebound_attribute_assign_call_is_captured(tmp_path: Path) -> None:
    """`f = importlib.import_module` + `f("_h")` is captured (Attribute RHS).

    Red-before (45decab): name `f` ∉ frozenset → frozenset().
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\nf = importlib.import_module\n_h = f('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_alias_of_alias_call_is_captured(tmp_path: Path) -> None:
    """Adversarial: `import_module as im` then `g = im` then `g("_h")` is captured.

    Exercises the fixpoint Assign folding (intra-file order independence).
    Red-before (45decab): both `im` and `g` ∉ frozenset → frozenset().
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from importlib import import_module as im\ng = im\n_h = g('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


# ---------------------------------------------------------------------------
# (3) **kwargs splat — statically irreducible → fail closed (G1)
# ---------------------------------------------------------------------------


def test_kwargs_splat_fails_closed(tmp_path: Path) -> None:
    """`import_module(**k)` (no resolvable name) fails closed like the variable arg.

    Red-before (45decab): `arg is None` → silent `continue` → frozenset() (no raise).
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\nk = {'name': '_dyn_helper'}\n_h = importlib.import_module(**k)\n",
    )
    with pytest.raises(mod.DetectorScopeError, match=r"\*\*kwargs"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_name_keyword_plus_splat_is_captured(tmp_path: Path) -> None:
    """`import_module(name="_h", **extra)`: name is resolvable, splat ignored → captured.

    Boundary-pin: the module name IS statically known, so the splat cannot change
    WHICH module loads; fail-closed would be a false positive. (Not red-before:
    pre-fix `arg is None` was False here too, but `name` keyword resolved — the
    pre-fix path already captured this; pinned to guard against the kwargs-splat
    fix over-firing.)
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module(name='_dyn_helper', **{})\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


def test_plain_zero_arg_call_is_ignored(tmp_path: Path) -> None:
    """`import_module()` (no args, no splat) imports nothing → ignored, no raise.

    Boundary-pin: distinguishes the zero-arg case from the **kwargs-splat case so
    the fail-closed branch does not over-fire on a degenerate (but harmless) call.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "import importlib\n_h = importlib.import_module()\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# Over-capture guard: user-defined callable named like an import callable
# ---------------------------------------------------------------------------


def test_user_function_named_im_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: a user `def im(x)` is NOT folded into the recognized set.

    `im` is bound by a function def, not an import alias / recognized Assign, so
    `im("_h")` must NOT capture `_h`. Boundary-pin (pre- and post-fix both
    frozenset()): guards the alias-folding from going name-only.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "def im(x):\n    return x\n_h = im('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")  # exists but must NOT be captured
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_user_assign_to_non_import_callable_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: `f = some_other_func` is NOT folded (RHS not recognized).

    Boundary-pin: the Assign-rebind pass must only fold when the RHS is a
    recognized import callable, not any Name/Attribute.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import os\nf = os.getcwd\n_h = f('_dyn_helper')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")  # exists but must NOT be captured
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# S5U-1100: relative dynamic literal now resolved (was an S5U-1098 carve-out)
# ---------------------------------------------------------------------------


def test_relative_dynamic_literal_resolved_s5u_1100(tmp_path: Path) -> None:
    """S5U-1100: `import_module("._h", package="scripts")` now resolves the sibling.

    This shape silently escaped (frozenset()) under S5U-1098, pinned here as an
    out-of-scope carve-out owned by S5U-1100. S5U-1100 resolves it: the constant
    `package="scripts"` anchor strips the leading dot and routes `_dyn_helper`
    through `_dotted_candidate_names`, so the helper lands IN scope. Full
    coverage (positional package, fail-closed variants, over-capture guard) lives
    in `test_detector_source_scope_dynamic.py`; this is the boundary flip.
    """
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "import importlib\n_h = importlib.import_module('._dyn_helper', package='scripts')\n",
    )
    _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset({"scripts/_dyn_helper.py"})


# ---------------------------------------------------------------------------
# Split coverage claim: the new module is itself in safety-gate scope
# ---------------------------------------------------------------------------


def test_dynamic_import_scope_module_is_in_safety_gate_scope() -> None:
    """The split-out `scripts/_dynamic_import_scope.py` is captured by the real-repo scope.

    The new module is `_`-prefixed and NOT matched by the static name regex; it is
    load-bearing safety-gate logic. It must land in `import_graph_scope()` of the
    real repo (via the closure from `check_post_merge_coordinator_ack.py` →
    `_detector_source_scope` → `_dynamic_import_scope`), or the split created an
    unprotected helper. Boundary-pin against the real tree (S5U-1098).
    """
    mod = _load()
    scope = mod.import_graph_scope(repo_root=REPO)
    assert "scripts/_dynamic_import_scope.py" in scope
    assert "scripts/_detector_source_scope.py" in scope

"""S5U-1102: non-simple rebind / open-ended binding shapes of import_module.

S5U-1098 made the dynamic-import recognized-callable set content-derived but
``_dynamic_import_callables`` folded only ``ImportFrom`` aliases + **simple**
``ast.Assign`` (single ``Name`` target). Four sibling binding shapes in the same
evasion class still escaped silently (no capture, no fail-closed):

1. **AnnAssign** — ``im: object = import_module`` then ``im("_h")``.
2. **Chained Assign** — ``a = b = import_module`` then ``a("_h")``.
3. **Tuple-unpack** — ``im, other = import_module, None`` then ``im("_h")``.
4. **Walrus** — ``(im := import_module)("_h")`` / ``x = (im := import_module); im(...)``.

S5U-1102 closes the CLASS (not four more shapes): it folds the statically
resolvable rebinds (AnnAssign + chained Assign — both captured here) and adds a
conservative catch-all (``_assert_no_unmodeled_callable_ref``) that FAILS CLOSED
on any recognized-callable reference outside a modeled position (a folded RHS or a
direct-call ``func``). Tuple-unpack, walrus, default-arg, decorator, container
literal, lambda body, and any future novel binding shape therefore become a loud
``DetectorScopeError`` refusal instead of a silent escape.

These tests live in a separate module from
``test_detector_source_scope_dynamic_shapes.py`` (at 271 lines) to keep both files
under the 400-line source-length cap.

Red-before (all new tests): at pre-fix tree ``cbf7062`` (main), every shape below
returned ``frozenset()`` — silent escape, no capture and no raise. Captured by a
local run at ``cbf7062`` reverting the fix:

    PRE-FIX (main, cbf7062) behavior:
      AnnAssign : frozenset()
      chained   : frozenset()
      tuple     : frozenset()
      walrus-cl : frozenset()
      walrus-as : frozenset()
      defaultarg: frozenset()
      dict      : frozenset()
      list      : frozenset()
      lambda    : frozenset()

The capture tests (AnnAssign / chained) now assert ``frozenset({...})`` (red-before:
``frozenset()``); the refusal tests now assert ``pytest.raises`` (red-before: no
raise, ``frozenset()``). The boundary-pin tests (plain import resolves, def im not
over-captured, live repo) pass in both states — framed as such below, NOT red-before.
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


def _scope_of(tmp_path: Path, body: str, *, helper: bool = True) -> frozenset[str]:
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", body)
    if helper:
        _write_script(scripts, "_dyn_helper.py", "X = 1\n")
    return mod.import_graph_scope(repo_root=tmp_path)


# Common preamble for the synthetic check_foo.py bodies (keeps lines under the cap).
_IMP = "from importlib import import_module\n"
_CALL = "_h = im('_dyn_helper')\n"


# ---------------------------------------------------------------------------
# (1) / (2) Foldable rebinds — AnnAssign + chained Assign → captured
# ---------------------------------------------------------------------------


def test_annassign_rebind_call_is_captured(tmp_path: Path) -> None:
    """`im: object = import_module` + `im("_h")` is captured (AnnAssign fold).

    Red-before (cbf7062): AnnAssign is not ast.Assign → Pass 2 never saw it →
    frozenset() (silent escape).
    """
    scope = _scope_of(
        tmp_path,
        "from importlib import import_module\nim: object = import_module\n_h = im('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_chained_assign_rebind_call_is_captured(tmp_path: Path) -> None:
    """`a = b = importlib.import_module` + `a("_h")` is captured (chained Assign).

    Red-before (cbf7062): the `len(node.targets) == 1` guard skipped the chained
    Assign → frozenset() (silent escape).
    """
    scope = _scope_of(
        tmp_path,
        "import importlib\na = b = importlib.import_module\n_h = a('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_chained_assign_second_target_call_is_captured(tmp_path: Path) -> None:
    """Chained Assign folds ALL Name targets: `a = b = import_module` + `b("_h")`.

    Red-before (cbf7062): chained Assign skipped entirely → frozenset(). Pins that
    the fold iterates every Name target, not just the first.
    """
    scope = _scope_of(
        tmp_path,
        "from importlib import import_module\na = b = import_module\n_h = b('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_annassign_alias_of_alias_is_captured(tmp_path: Path) -> None:
    """Fixpoint over AnnAssign: `import_module as im` then `g: object = im` + `g("_h")`.

    Red-before (cbf7062): AnnAssign unseen → `g` ∉ recognized → frozenset().
    Exercises the fold reaching a fixpoint through an annotated rebind.
    """
    scope = _scope_of(
        tmp_path,
        "from importlib import import_module as im\ng: object = im\n_h = g('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


# ---------------------------------------------------------------------------
# (3) / (4) + catch-all — open-ended binding shapes → fail closed (G1)
# ---------------------------------------------------------------------------


def test_tuple_unpack_rebind_fails_closed(tmp_path: Path) -> None:
    """`im, other = import_module, None` + `im("_h")` fails closed (catch-all).

    Red-before (cbf7062): Tuple target skipped, Tuple RHS unseen → frozenset()
    (silent escape). Tuple-unpack is open-ended → refuse, don't fold.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "im, other = import_module, None\n" + _CALL)


def test_walrus_in_call_position_fails_closed(tmp_path: Path) -> None:
    """`(im := import_module)("_h")` fails closed (walrus in direct-call position).

    Red-before (cbf7062): NamedExpr is neither pass's shape; `_call_func_name` on a
    NamedExpr func returns None → frozenset() (silent escape).
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "_h = (im := import_module)('_dyn_helper')\n")


def test_walrus_in_assign_position_fails_closed(tmp_path: Path) -> None:
    """`x = (im := import_module); im("_h")` fails closed (walrus in binding position).

    Red-before (cbf7062): NamedExpr unseen, `im` ∉ recognized → frozenset().
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "x = (im := import_module)\n" + _CALL)


def test_default_arg_binding_fails_closed(tmp_path: Path) -> None:
    """`def f(im=import_module): return im("_h")` fails closed (default-arg bind).

    Red-before (cbf7062): default value is in `args.defaults`, not a fold position
    → frozenset(). Catch-all refuses the import callable bound as a default arg.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "def f(im=import_module):\n    return im('_dyn_helper')\n")


def test_dict_containment_fails_closed(tmp_path: Path) -> None:
    """`d = {"f": import_module}; d["f"]("_h")` fails closed (container literal).

    Red-before (cbf7062): container-mediated rebind escaped silently → frozenset().
    S5U-1102 strengthens the literal-binding-site case to a refusal (the recognized
    Name is visible in the dict literal). String-keyed read stays a residual.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "d = {'f': import_module}\n_h = d['f']('_dyn_helper')\n")


def test_list_containment_fails_closed(tmp_path: Path) -> None:
    """`lst = [import_module]; lst[0]("_h")` fails closed (list literal containment).

    Red-before (cbf7062): list-element rebind escaped silently → frozenset().
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "lst = [import_module]\n_h = lst[0]('_dyn_helper')\n")


def test_lambda_body_bare_ref_fails_closed(tmp_path: Path) -> None:
    """`f = lambda: import_module` + `f()("_h")` fails closed (lambda-body bare ref).

    Red-before (cbf7062): the lambda body's bare `import_module` reference was never
    a fold/call position the scan modeled → frozenset() (silent escape).
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _IMP + "f = lambda: import_module\n_h = f()('_dyn_helper')\n")


# ---------------------------------------------------------------------------
# S5U-1110 — multi-level attribute (`a.b.import_module`) in non-fold positions
# must fail closed, mirroring the value-agnostic fold recognizer. Pre-1110 the
# catch-all's Attribute branch required `value` be a `Name` (single-level only),
# so a multi-level chain folded in a simple-assign yet silently escaped here.
# ---------------------------------------------------------------------------

_MLA = "import a.b\n"  # the multi-level attribute preamble (`a.b.import_module`)


def test_multi_level_attr_tuple_fails_closed(tmp_path: Path) -> None:
    """`im, _ = a.b.import_module, None` + `im("_h")` fails closed (multi-level attr).

    Red-before: at pre-fix main (2f93172) this returned frozenset() — the catch-all's
    `isinstance(node.value, ast.Name)` clause made the multi-level Attribute reference
    invisible, so it silently escaped (no capture, no raise). Local run at 2f93172:
    `tuple multi-level: set()`.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _MLA + "im, other = a.b.import_module, None\n_h = im('_dyn_helper')\n")


def test_multi_level_attr_walrus_fails_closed(tmp_path: Path) -> None:
    """`(im := a.b.import_module)("_h")` fails closed (multi-level attr walrus).

    Red-before: at pre-fix main (2f93172) this returned frozenset() (silent escape).
    Local run at 2f93172: `walrus multi-level: set()`.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _MLA + "_h = (im := a.b.import_module)('_dyn_helper')\n")


def test_multi_level_attr_default_arg_fails_closed(tmp_path: Path) -> None:
    """`def f(im=a.b.import_module): return im("_h")` fails closed (multi-level attr).

    Red-before: at pre-fix main (2f93172) this returned frozenset() (silent escape).
    Local run at 2f93172: `defaultarg multi-level: set()`.
    """
    with pytest.raises(_load().DetectorScopeError, match="binding/escape position"):
        _scope_of(tmp_path, _MLA + "def f(im=a.b.import_module):\n    return im('_dyn_helper')\n")


# ---------------------------------------------------------------------------
# False-positive / over-capture guards — must NOT raise, must NOT over-capture
# (boundary-pins: pass in BOTH pre- and post-fix states; NOT red-before)
# ---------------------------------------------------------------------------


def test_plain_import_direct_call_still_resolves(tmp_path: Path) -> None:
    """Boundary-pin: plain `from importlib import import_module` + direct call resolves.

    The catch-all must NOT refuse the legitimate import + direct-call path: the
    import is an ast.alias (no Name node) and the call func is a modeled position.
    Pass in both states — guards the catch-all from over-firing.
    """
    scope = _scope_of(
        tmp_path,
        "from importlib import import_module\n_h = import_module('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_attribute_direct_call_still_resolves(tmp_path: Path) -> None:
    """Boundary-pin: `importlib.import_module("_h")` (attribute direct call) resolves.

    The `importlib.import_module` Attribute is the func of a Call (modeled). Pass in
    both states.
    """
    scope = _scope_of(
        tmp_path,
        "import importlib\n_h = importlib.import_module('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_attribute_rhs_fold_still_resolves(tmp_path: Path) -> None:
    """Boundary-pin: `f = importlib.import_module` + `f("_h")` still folds + resolves.

    The Attribute RHS is a folding position; the catch-all must mark it modeled so
    the S5U-1098 attribute-rebind path does not regress. Pass in both states.
    """
    scope = _scope_of(
        tmp_path,
        "import importlib\nf = importlib.import_module\n_h = f('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_multi_level_attr_simple_assign_still_resolves(tmp_path: Path) -> None:
    """Symmetry pin: `im = a.b.import_module` + `im("_h")` still folds + resolves.

    The fold's `_expr_recognized_seed` recognizes an Attribute value-agnostically, so a
    multi-level chain folds in a simple-assign position. S5U-1110 widens the catch-all
    to match — this pin locks the symmetry: the modeled fold path must NOT regress when
    the catch-all widens. Passes in BOTH pre- and post-fix states (pre-fix already
    captured it: local run at 2f93172 `simpleasn multi-level: {'_helper'}`), so this is
    a boundary-pin, NOT red-before.
    """
    scope = _scope_of(
        tmp_path,
        "import a.b\nim = a.b.import_module\n_h = im('_dyn_helper')\n",
    )
    assert scope == frozenset({"scripts/_dyn_helper.py"})


def test_user_def_named_im_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: a user `def im(x)` is NOT folded and NOT refused.

    `im` is bound by a function def, not an import alias / fold, so it is never in
    `recognized`; the catch-all therefore sees no recognized reference. Must be
    frozenset() with no raise. Pass in both states.
    """
    scope = _scope_of(
        tmp_path,
        "def im(x):\n    return x\n_h = im('_dyn_helper')\n",
    )
    assert scope == frozenset()


def test_non_recognized_assign_rhs_not_over_captured(tmp_path: Path) -> None:
    """Over-capture guard: `f = os.getcwd` is neither folded nor refused.

    The RHS Attribute `os.getcwd` is not a recognized callable, so `f` ∉ recognized
    and `os.getcwd` is not a recognized reference → no fold, no refusal, frozenset().
    Pass in both states.
    """
    scope = _scope_of(
        tmp_path,
        "import os\nf = os.getcwd\n_h = f('_dyn_helper')\n",
    )
    assert scope == frozenset()


def test_string_mention_does_not_trip_catch_all(tmp_path: Path) -> None:
    """Over-strictness guard: a string literal `"import_module"` is not a reference.

    Only Name/Attribute references count; a Constant string is never walked as a
    reference, so a docstring / string mention must not trip the refusal. Pass in
    both states.
    """
    scope = _scope_of(
        tmp_path,
        '"""mentions import_module in prose"""\nimport os\n_h = os.getcwd()\n',
        helper=False,
    )
    assert scope == frozenset()


def test_live_repo_scope_still_computes_cleanly() -> None:
    """Boundary-pin: the real-repo `import_graph_scope` still computes (no refusal).

    The catch-all must not refuse any in-scope detector / helper in the live tree.
    The split-out module must remain in scope (S5U-1098 invariant). Pass in both
    states (the catch-all is the only new failure surface; the live tree has no
    open-ended import-callable binding).
    """
    mod = _load()
    scope = mod.import_graph_scope(repo_root=REPO)
    assert "scripts/_dynamic_import_scope.py" in scope
    assert "scripts/_detector_source_scope.py" in scope

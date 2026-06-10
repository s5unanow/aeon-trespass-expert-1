"""Dynamic-import (importlib / ``__import__``) sibling-helper resolution (S5U-996, S5U-1098).

Split out of ``scripts/_detector_source_scope.py`` (S5U-1098) to keep that module
under the 400-line source cap. This module owns the AST logic that resolves which
sibling ``scripts/_*.py`` helpers a detector reaches via a *dynamic* import call
(``import_module(...)`` / ``__import__(...)``), as opposed to a static
``import`` / ``from … import`` edge.

It is a leading-underscore sibling brought into the content-derived safety-gate
scope ONLY via the import-graph closure: ``_detector_source_scope.py`` does
``from _dynamic_import_scope import …`` (bare sibling import), and that module is
itself walked transitively from the in-scope ``scripts/check_post_merge_coordinator_ack.py``
detector. A lone edit here is therefore captured by the coordinator-ack pre-PR
refusal + post-merge audit, the same as the deriver it serves. (Verified by the
``--list`` output containing ``scripts/_dynamic_import_scope.py`` and by a
real-repo regression test.)

## Recognized-callable set is content-derived per file (S5U-1098, Rule G2)

S5U-996 matched dynamic-import calls by callable name only against the frozen
set ``{"import_module", "__import__"}``. Three semantically-``import_module`` /
``__import__`` shapes escaped silently — a Rule-G2 name-derived weakness where a
rename / rebind bypasses a content-protecting guard:

1. **Aliased import** — ``from importlib import import_module as im`` then
   ``im("_h")``. The callable name ``im`` is not in the frozen set.
2. **Rebound name** — ``imp = __import__`` (or ``f = importlib.import_module``)
   then ``imp("_h")`` / ``f("_h")``.
3. ``**kwargs`` **call shape** — ``import_module(**k)``: no positional, no
   ``name=`` keyword, so the module name is statically irreducible (exactly like
   the variable-arg case that already fails closed) yet it fell through silently.

``_dynamic_import_callables(tree)`` derives, per source file, the set of local
names that are bound to ``import_module`` / ``__import__`` — the seed
``{"import_module", "__import__"}`` plus every ``ImportFrom`` / ``Import``
``asname`` that binds one of them, plus every simple ``Assign`` that rebinds a
name to an already-recognized callable (to a fixpoint, so intra-file ordering
is irrelevant). The over-capture guard: a name is folded ONLY when an actual
``import`` alias or an ``Assign`` whose RHS is a recognized callable binds it — a
user-defined ``def im(...)`` produces neither, so it is never folded.

## Residuals (honest static-analysis boundary)

- **Cross-file** alias/rebind (the alias is imported from another module, or a
  callable is rebound in module A and used in module B) is NOT resolved — this
  is single-file AST only.
- **Container-mediated rebind** (``d = {"f": import_module}; d["f"]("_h")``,
  ``getattr(importlib, "import_module")("_h")``) is NOT resolved.
- **Relative dynamic literal** ``import_module("._helper", package="scripts")`` is
  resolved (S5U-1100): a single-level relative literal anchored on the constant
  ``package="scripts"`` strips the leading dot and routes through the dotted-candidate
  resolver (``"._helper"`` -> ``_helper``); package absent / non-constant / any other
  constant / multi-level (``".._h"``) fails closed (``DetectorScopeError``), mirroring
  the non-constant module-name branch. The builtin ``__import__`` has no string
  ``package`` anchor (it uses an integer ``level``), so a leading-dot literal there
  fails closed too.
- **Bespoke loaders** (``exec`` / ``runpy`` / custom importlib machinery) are the
  pre-existing S5U-996 residual. Backstop for all of these: corpus declaration.
- A non-import callable that is *named* ``import_module`` / ``__import__`` (or an
  alias thereof) and called with ``**kwargs`` now fails closed — a conservative
  false-positive accepted because such a name collision is itself a red flag and
  fail-closed is the Rule-G1-correct direction for a statically irreducible call.
"""

from __future__ import annotations

import ast

# Seed dynamic-import callables (S5U-996). The per-file recognized set is this
# seed UNIONed with content-derived aliases / rebinds (S5U-1098). Matched as a
# bare name (``import_module`` via ``from importlib import import_module``) or an
# attribute (``importlib.import_module``).
_DYNAMIC_IMPORT_NAMES = frozenset({"import_module", "__import__"})

# The flat-sibling package anchor the deriver models (``scripts/_*.py``). A
# relative dynamic literal resolves only when its ``package`` argument is this
# exact constant (S5U-1100).
_SCRIPTS_PACKAGE = "scripts"


class DetectorScopeError(RuntimeError):
    """Raised when a corpus or detector source is present but unreadable (G1).

    Defined here so this module is import-cycle-free; re-exported by
    ``_detector_source_scope`` for the public API surface.
    """


def _call_func_name(node: ast.Call) -> str | None:
    """Return the callable's rightmost identifier, else None.

    ``import_module(...)`` and ``importlib.import_module(...)`` both surface as
    ``import_module`` (``ast.Name`` / ``ast.Attribute``).
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _expr_recognized_name(expr: ast.expr, recognized: set[str]) -> bool:
    """Return True if *expr* refers to an already-recognized dynamic-import callable.

    Covers a bare ``ast.Name`` RHS (``imp = __import__`` / ``g = im``) and an
    ``ast.Attribute`` RHS (``f = importlib.import_module``). The ``Name`` case
    keys on the accumulated *recognized* set so an alias-of-alias resolves once
    the seed alias is folded.
    """
    if isinstance(expr, ast.Name):
        return expr.id in recognized
    if isinstance(expr, ast.Attribute):
        return expr.attr in _DYNAMIC_IMPORT_NAMES
    return False


def _dynamic_import_callables(tree: ast.AST) -> frozenset[str]:
    """Derive the per-file set of local names bound to import_module / __import__.

    Content-derived (Rule G2): the seed ``{"import_module", "__import__"}`` plus
    every ``import`` ``asname`` that binds one of them, plus every simple
    ``Assign`` whose RHS is an already-recognized callable. Assign folding runs
    to a fixpoint so intra-file ordering (``ast.walk`` is BFS, not source order)
    cannot leave an alias-of-alias unresolved.
    """
    recognized: set[str] = set(_DYNAMIC_IMPORT_NAMES)

    # Pass 1 — import aliases. ``from importlib import import_module as im`` and
    # ``from builtins import __import__ as imp`` bind a local alias; fold it.
    # A plain ``import importlib as il`` binds the *module*, not the callable, so
    # its asname is NOT folded (the attribute form ``il.import_module`` is matched
    # at call time via ``_call_func_name`` instead).
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"importlib", "builtins"}:
            for alias in node.names:
                if alias.name in _DYNAMIC_IMPORT_NAMES and alias.asname:
                    recognized.add(alias.asname)

    # Pass 2 — simple Assign rebinds, to a fixpoint. ``imp = __import__``,
    # ``g = im`` (alias-of-alias), ``f = importlib.import_module``.
    assigns: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assigns.append((target.id, node.value))
    changed = True
    while changed:
        changed = False
        for name, value in assigns:
            if name not in recognized and _expr_recognized_name(value, recognized):
                recognized.add(name)
                changed = True

    return frozenset(recognized)


def _dynamic_import_arg(node: ast.Call) -> ast.expr | None:
    """Return the module-name arg of a dynamic-import call (positional or ``name=``).

    Both callables name the first param ``name``, so the keyword form
    (``import_module(name="_h")``) is handled like the positional, not skipped.
    A ``**kwargs`` splat (``ast.keyword`` with ``arg is None``) carries no
    resolvable name and is NOT returned here — the caller distinguishes
    "no name at all + splat present" (fail closed) from "plain zero-arg" (ignore).
    """
    if node.args:
        return node.args[0]
    return next((kw.value for kw in node.keywords if kw.arg == "name"), None)


def _has_kwargs_splat(node: ast.Call) -> bool:
    """Return True if the call has a ``**kwargs`` splat (``ast.keyword`` arg=None)."""
    return any(kw.arg is None for kw in node.keywords)


# Sentinel: ``_package_arg`` returns this when the ``package`` argument is absent
# entirely, distinguishing "no anchor at all" from "anchor present but non-constant".
_PACKAGE_ABSENT = object()


def _package_arg(node: ast.Call) -> object | None:
    """Return the ``package`` anchor of an ``import_module`` call (S5U-1100).

    ``importlib.import_module(name, package=None)`` — ``package`` is the SECOND
    positional argument (``node.args[1]``) or the ``package=`` keyword. Returns the
    constant string value when it is a string literal; ``None`` when the anchor is
    present but non-constant (variable / f-string / non-str); ``_PACKAGE_ABSENT``
    when there is no ``package`` argument at all. The caller distinguishes these:
    a constant ``"scripts"`` resolves, every other state fails closed.
    """
    pkg: ast.expr | None = None
    if len(node.args) >= 2:
        pkg = node.args[1]
    else:
        pkg = next((kw.value for kw in node.keywords if kw.arg == "package"), None)
    if pkg is None:
        return _PACKAGE_ABSENT
    if isinstance(pkg, ast.Constant) and isinstance(pkg.value, str):
        return pkg.value
    return None  # present but non-constant — statically irreducible


def _resolve_relative_literal(
    literal: str,
    node: ast.Call,
    rel: str,
    dotted_candidates: object,
) -> set[str]:
    """Resolve a leading-dot dynamic literal against its ``package`` anchor (S5U-1100).

    A relative dynamic literal (``import_module("._h", package="scripts")``) is
    statically resolvable ONLY when ``package`` is the constant ``"scripts"`` and
    the literal is a single-level relative reference (one leading dot). In that case
    the dot is stripped and the remainder routed through ``_dotted_candidate_names``
    exactly like the absolute path (``"._h"`` -> ``"_h"``). Every other state —
    package absent / non-constant / a constant other than ``"scripts"`` / multi-level
    relative (``".._h"``, which escapes the flat ``scripts/_*.py`` sibling model) —
    is statically irreducible for the flat-sibling deriver, so it fails closed
    (``DetectorScopeError``) per .claude/rules/guards.md Rule G1, mirroring the
    non-constant module-name branch.
    """
    package = _package_arg(node)
    callable_name = _call_func_name(node)
    leading = len(literal) - len(literal.lstrip("."))
    if package == _SCRIPTS_PACKAGE and leading == 1:
        # ``"._h"`` -> ``"_h"`` -> route through the dotted-candidate resolver.
        return dotted_candidates(literal.lstrip("."))  # type: ignore[operator,no-any-return]
    raise DetectorScopeError(
        f"detector source {rel} line {node.lineno}: dynamic import "
        f"({callable_name}) with a relative module name {literal!r} cannot resolve "
        "a sibling helper statically unless `package` is the constant 'scripts' and "
        "the reference is single-level (one leading dot). Per .claude/rules/guards.md "
        "Rule G1, fail closed: make the import static (`from _helper import ...`) OR "
        "declare the helper in a corpus `detector_sources` list."
    )


def dynamic_helper_names(
    source: str,
    rel: str,
    dotted_candidates: object,
) -> set[str]:
    """Return sibling-helper names reached via dynamic import in *source*.

    *dotted_candidates* is the ``_dotted_candidate_names`` callable from
    ``_detector_source_scope`` (passed in to avoid an import cycle); a string
    literal is routed through it exactly like the static path (S5U-1097), so
    ``import_module("scripts._helper")`` yields ``_helper`` not the dropped
    ``scripts``.

    The recognized-callable set is content-derived per file
    (``_dynamic_import_callables``), so aliased / rebound forms are matched
    (S5U-1098). Fail-closed (``DetectorScopeError``) on a statically irreducible
    module name: a non-constant arg (variable / f-string) OR a ``**kwargs`` splat
    with no resolvable ``name`` (S5U-1098 item 3). A plain zero-arg call of a
    recognized-named callable (``import_module()``) is ignored — it imports
    nothing.
    """
    callables = _dynamic_import_callables(ast.parse(source))
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if _call_func_name(node) not in callables:
            continue
        arg = _dynamic_import_arg(node)
        if arg is None:
            if _has_kwargs_splat(node):
                # ``import_module(**k)``: statically irreducible, like a variable
                # arg. Fail closed (G1) rather than silently under-capture.
                raise DetectorScopeError(
                    f"detector source {rel} line {node.lineno}: dynamic import "
                    f"({_call_func_name(node)}) with a `**kwargs` splat and no "
                    "resolvable `name` cannot resolve a sibling helper statically. "
                    "Per .claude/rules/guards.md Rule G1, fail closed: make the "
                    "import static (`from _helper import ...`) OR declare the "
                    "helper in a corpus `detector_sources` list."
                )
            # Plain zero-arg call of a recognized-named callable imports nothing.
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value.startswith("."):
                # Relative literal (``import_module("._h", package="scripts")``):
                # resolve against the ``package`` anchor or fail closed (S5U-1100).
                names |= _resolve_relative_literal(arg.value, node, rel, dotted_candidates)
            else:
                names |= dotted_candidates(arg.value)  # type: ignore[operator]
            continue
        # Non-constant module name: statically irreducible. Fail closed (G1).
        raise DetectorScopeError(
            f"detector source {rel} line {node.lineno}: dynamic import "
            f"({_call_func_name(node)}) with a non-constant module name cannot "
            "resolve a sibling helper statically. Per .claude/rules/guards.md "
            "Rule G1, fail closed: make the import static (`from _helper import "
            "...`) OR declare the helper in a corpus `detector_sources` list."
        )
    return names

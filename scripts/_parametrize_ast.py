"""AST alias-resolution helper for the parametrize red-before detector (S5U-920).

Split out of `scripts/check_parametrize_red_before.py` to keep that file under
the 400-line ceiling. This module is a `detector_source` of the
`parametrize_red_before` corpus alongside the main detector, so a change here
without a matching corpus update fails the coverage gate
(`scripts/check_detector_corpus_coverage.py`).

Rule G2 (content-derived over name-derived, `.claude/rules/guards.md`): the
detector's decorator-name checks compare a decorator's root binding against the
*resolved* canonical import target rather than the surface name an
`import ... as <alias>` rename produced. That closes the alias-rename bypass
class (`from pytest import mark as m2; @m2.parametrize`) the name-anchored
`id == "mark"` check missed.
"""

from __future__ import annotations

import ast


def collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    """Map each local binding name to its canonical dotted import target.

    Walks every `ast.Import` / `ast.ImportFrom` node and records, e.g.::

        import pytest.mark as pm            -> {"pm": "pytest.mark"}
        from pytest import mark             -> {"mark": "pytest.mark"}
        from pytest import mark as m2       -> {"m2": "pytest.mark"}
        from pytest.mark import parametrize -> {"parametrize": "pytest.mark.parametrize"}

    Unaliased rows record the identity/canonical mapping too, so the existing
    unaliased forms resolve identically and keep matching (no regression).
    Later occurrences win, mirroring Python rebinding.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # `import a.b as c` binds c->a.b; bare `import a.b` binds the head a->a.
                local = alias.asname if alias.asname is not None else alias.name.split(".")[0]
                aliases[local] = alias.name if alias.asname is not None else local
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local = alias.asname if alias.asname is not None else alias.name
                aliases[local] = f"{node.module}.{alias.name}"
    return aliases


def decorator_context_label(decorator: ast.expr, aliases: dict[str, str]) -> str | None:
    """Return a short label if `decorator` matches a parametrize-equivalent shape.

    Content-derived AST match per .claude/rules/guards.md Rule G2 over the
    canonical pytest / hypothesis decorator vocabulary. Decorator root names are
    resolved through `aliases` first (S5U-920) so `import ... as <alias>` renames
    match against the canonical target, not the surface name.
    """
    inner = decorator.func if isinstance(decorator, ast.Call) else decorator

    # @<x>.mark.parametrize(...) — dotted chain. Root-agnostic structural match on
    # the `.attr` names, preserving pre-S5U-920 behavior so this change never
    # NARROWS the gate (covers @pytest.mark.parametrize and @pt.mark.parametrize).
    if (
        isinstance(inner, ast.Attribute)
        and inner.attr == "parametrize"
        and isinstance(inner.value, ast.Attribute)
        and inner.value.attr == "mark"
    ):
        return "pytest.mark.parametrize"

    # @<name>.parametrize(...) — single-Name form (@mark./@m2./@pm.parametrize).
    # S5U-920: resolve `<name>` through the import-alias map; match only when it
    # canonically binds to `pytest.mark`, so `import ... as <alias>` renames flag
    # by content (Rule G2) while `@myteam.parametrize` stays out of scope. The
    # literal-name fallbacks preserve prior behavior when the import was
    # uncaptured (star-import / dynamic binding).
    if (
        isinstance(inner, ast.Attribute)
        and inner.attr == "parametrize"
        and isinstance(inner.value, ast.Name)
        and (
            aliases.get(inner.value.id) == "pytest.mark"
            or (inner.value.id == "mark" and inner.value.id not in aliases)
        )
    ):
        return "mark.parametrize"

    # bare @parametrize(...) — `from pytest.mark import parametrize` (or `as p`).
    if isinstance(inner, ast.Name) and (
        aliases.get(inner.id) == "pytest.mark.parametrize"
        or (inner.id == "parametrize" and inner.id not in aliases)
    ):
        return "parametrize"

    # @given(...) (hypothesis) — alias-resolved Name + root-agnostic attr fallback.
    if isinstance(inner, ast.Name) and (
        aliases.get(inner.id) == "hypothesis.given"
        or (inner.id == "given" and inner.id not in aliases)
    ):
        return "given"
    if isinstance(inner, ast.Attribute) and inner.attr == "given":
        return "given"

    # @pytest.fixture(..., params=[...]) — only flag if `params=` keyword is
    # present (otherwise it's an ordinary fixture, not parametrized).
    if isinstance(decorator, ast.Call):
        is_fixture = (
            isinstance(inner, ast.Attribute)
            and inner.attr == "fixture"
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "pytest"
        ) or (isinstance(inner, ast.Name) and inner.id == "fixture")
        if is_fixture and any(kw.arg == "params" for kw in decorator.keywords):
            return "pytest.fixture(params=...)"

    return None

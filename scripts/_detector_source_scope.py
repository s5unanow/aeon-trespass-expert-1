"""Content-derived safety-gate scope: corpus ``detector_sources`` + import graph.

S5U-922. The safety-gate scope matchers in ``.claude/hooks/pre-pr-check.sh`` and
``scripts/check_post_merge_coordinator_ack.py`` historically matched only
``scripts/check_*.{sh,py}`` and ``scripts/pre-*.{sh,py}`` by name. S5U-920
extracted the load-bearing parametrize-detector decorator logic into the sibling
``scripts/_parametrize_ast.py`` — a leading-underscore path that matches neither
clause. A future lone edit to that file (or any of the
``scripts/_instruction_drift_rule_*.py`` helpers, which escape the same way)
would bypass the pre-PR coordinator-ack refusal and the post-merge audit.

This module closes that gap the Rule-G2 (``.claude/rules/guards.md``)
content-derived way. The in-scope set is the UNION of two content-derived layers,
never a hardcoded name list:

1. **Corpus layer (S5U-922)** — the union of every corpus's ``detector_sources``
   list. The corpus is the authoritative contract for "which files carry
   load-bearing detector logic" (it is what ``check_detector_corpus_coverage.py``
   binds against). It also covers non-``scripts/_*.py`` declared sources (e.g.
   ``.claude/prompts/review.md``) that the import graph cannot reach.
2. **Import-graph layer (S5U-926)** — for every in-scope detector
   (``scripts/check_*.py`` / ``scripts/pre-*.py``), parse its ``import`` AST and
   fold in the transitive closure of sibling ``scripts/_*.py`` modules it
   imports. This makes "load-bearing == imported by an in-scope detector" the
   contract, so a future extracted helper is captured WITHOUT a human
   remembering to declare it in a corpus — the exact dependency that left
   ``_instruction_drift_rule_d.py``, ``_erosion_report_fmt.py``,
   ``_hotspot_budgets.py``, ``_repo_summary.py``, and ``_linear_client.py`` out
   of scope after S5U-922.

   The walk covers three edge styles (S5U-996 closed the latter two blind
   spots): bare sibling (``from _helper import f`` / ``import _helper as y``,
   incl. TYPE_CHECKING); dotted package (``from scripts._helper import f``, see
   ``_dotted_candidate_names``); and dynamic (``import_module("_helper")`` /
   ``__import__("_helper")``, see ``_dynamic_helper_names`` + G1 below).
   **Residual (S5U-996):** a helper loaded via a bespoke mechanism that is
   neither ``import_module`` / ``__import__`` nor a static ``import`` (custom
   loader, ``exec``, ``runpy``) is invisible to the AST scan; backstop is corpus
   declaration — the analogue of the S5U-926 shell-detector residual.

Both layers are content-derived: the corpus union is the declared contract; the
import graph is the actual ``ast`` import edges. A helper rename is auto-tracked
(the detector's import statement must change, or the detector breaks); a benign
underscore helper that no detector imports (``scripts/_export_*.py`` etc.) is NOT
over-captured.

Both safety-gate matchers consume THIS module so they cannot drift: the Python
audit imports ``detector_source_scope``; the bash hook shells out to the
``--list`` CLI. One source of truth.

## Rule G1 (fail-closed defaults)

Every degenerate input raises ``DetectorScopeError`` (CLI: exits non-zero with
the message on stderr):

- A corpus ``.toml`` that does not parse (``TOMLDecodeError`` / ``OSError``).
- A corpus missing a non-empty ``detector_sources`` list.
- A ``detector_sources`` entry that is not a non-empty string.
- A detector source the import-graph walk cannot read (``OSError``) or parse
  (``SyntaxError``). A detector the scope-deriver cannot read is NOT silently
  dropped from the walk — fail closed.
- A dynamic import (``import_module`` / ``__import__``, incl. aliased / rebound
  forms — S5U-1098) with a non-constant module name (variable / f-string) OR a
  ``**kwargs`` splat with no resolvable ``name`` (S5U-1098): statically
  irreducible, fail closed rather than silently under-capture (S5U-996).
  ``_dynamic_import_scope.dynamic_helper_names`` owns this logic; see that
  module's docstring for the recognized-callable derivation and residuals.

The ONLY non-raising degenerate cases are an **absent** corpus directory and an
**absent** ``scripts/`` directory: that means the caller is not running against
the real repo (e.g. a synthetic ``tmp_path`` unit-test repo), so there is no
detector contract to enforce and that layer contributes the empty set. The
real-repo callers pin ``repo_root`` to the actual repository root, which always
contains both directories.

Usage (CLI, one path per line on stdout):
    python scripts/_detector_source_scope.py --list
    python scripts/_detector_source_scope.py --list --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

from _dynamic_import_scope import DetectorScopeError, dynamic_helper_names

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = Path("apps/pipeline/tests/safety_gate_corpus")
DEFAULT_SCRIPTS_DIR = Path("scripts")

# In-scope detector filename globs (same surface the static safety-gate regex
# protects: scripts/check_*.py and scripts/pre-*.py). The import-graph walk
# starts from these and follows sibling scripts/_*.py imports transitively.
DETECTOR_GLOBS = ("check_*.py", "pre-*.py")


def corpus_source_scope(
    repo_root: Path | None = None,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> frozenset[str]:
    """Return the union of every corpus's ``detector_sources`` (repo-relative).

    Fail-closed (``DetectorScopeError``) on any malformed corpus file. An absent
    corpus directory returns an empty set (see module docstring — synthetic
    test repos legitimately have no corpus). The returned paths are exactly as
    declared in the corpus TOMLs (repo-relative POSIX strings).
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    abs_corpus_dir = corpus_dir if corpus_dir.is_absolute() else root / corpus_dir
    if not abs_corpus_dir.is_dir():
        return frozenset()

    sources: set[str] = set()
    for path in sorted(abs_corpus_dir.glob("*.toml")):
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise DetectorScopeError(
                f"cannot parse corpus {rel}: {exc}\n"
                "Per .claude/rules/guards.md Rule G1, parse errors fail closed."
            ) from exc

        declared = data.get("detector_sources")
        if not isinstance(declared, list) or not declared:
            raise DetectorScopeError(
                f"corpus {rel} is missing a non-empty `detector_sources` list.\n"
                "Per .claude/rules/guards.md Rule G1, fail closed."
            )
        for src in declared:
            if not isinstance(src, str) or not src:
                raise DetectorScopeError(
                    f"corpus {rel} has a non-string/empty `detector_sources` entry.\n"
                    "Per .claude/rules/guards.md Rule G1, fail closed."
                )
            sources.add(src)
    return frozenset(sources)


# Package the sibling helpers live under, so dotted ``scripts._helper`` resolves
# the sibling ``_helper`` instead of escaping as the first component ``scripts``
# (S5U-996). Special-casing only this one package avoids over-capturing arbitrary
# third-party dotted modules (``from foo.bar import x`` still yields only ``foo``).
_SCRIPTS_PACKAGE = "scripts"


def _dotted_candidate_names(dotted: str) -> set[str]:
    """Yield resolvable sibling-module candidates from a dotted module name.

    Always yields the first component; when it is the ``scripts`` package, also
    yields the second so ``scripts._helper`` resolves ``_helper`` (S5U-996). The
    ``_sibling_helper_path`` file-existence gate drops any non-existent component
    (no phantom capture).
    """
    parts = dotted.split(".")
    names = {parts[0]}
    if parts[0] == _SCRIPTS_PACKAGE and len(parts) >= 2:
        names.add(parts[1])
    return names


def _imported_module_names(source: str, rel: str) -> set[str]:
    """Return the sibling-module candidate names imported by *source* (AST-based).

    Walks every ``import`` / ``from … import`` node (incl. TYPE_CHECKING /
    function-nested — any static edge is load-bearing) via
    ``_dotted_candidate_names``, then folds in dynamic imports via
    ``dynamic_helper_names`` (``_dynamic_import_scope``). The caller resolves
    names against ``scripts/_*.py``.
    """
    names: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names |= _dotted_candidate_names(alias.name)
        # Skip relative imports (level > 0) — they don't name a sibling by bare
        # module name; the scripts/ helpers use absolute sibling imports
        # (sys.path.insert + `from _x import ...`).
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names |= _dotted_candidate_names(node.module)
    names |= dynamic_helper_names(source, rel, _dotted_candidate_names)
    return names


def _sibling_helper_path(name: str, scripts_dir: Path) -> Path | None:
    """Resolve *name* to a real sibling ``scripts/_<name>.py`` file, else None.

    Only leading-underscore module names that resolve to an existing file count.
    This drops ``__future__`` (no ``scripts/__future__.py``), stdlib, and
    third-party imports — they are not load-bearing detector helpers.
    """
    if not name.startswith("_"):
        return None
    candidate = scripts_dir / f"{name}.py"
    return candidate if candidate.is_file() else None


def import_graph_scope(
    repo_root: Path | None = None,
    scripts_dir: Path = DEFAULT_SCRIPTS_DIR,
) -> frozenset[str]:
    """Return the transitive sibling-helper closure of in-scope detectors.

    For every ``scripts/check_*.py`` / ``scripts/pre-*.py`` detector, parse its
    ``import`` AST and fold in every sibling ``scripts/_*.py`` it imports, then
    follow those helpers' own sibling imports transitively. Returns repo-relative
    POSIX paths of the captured helpers (NOT the detectors themselves — those are
    already matched by the static name regex).

    Fail-closed (``DetectorScopeError``) if any detector or helper source cannot
    be read (``OSError``) or parsed (``SyntaxError``). An absent ``scripts/``
    directory returns the empty set (synthetic-repo carve-out, symmetrical with
    the corpus layer).
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    abs_scripts_dir = scripts_dir if scripts_dir.is_absolute() else root / scripts_dir
    if not abs_scripts_dir.is_dir():
        return frozenset()

    # Seed the worklist with sibling helpers imported by each in-scope detector.
    worklist: list[Path] = []
    for glob in DETECTOR_GLOBS:
        for detector in sorted(abs_scripts_dir.glob(glob)):
            det_rel = _rel_posix(detector, root)
            for name in _imported_module_names(_read_python(detector, root), det_rel):
                helper = _sibling_helper_path(name, abs_scripts_dir)
                if helper is not None:
                    worklist.append(helper)

    # Transitive closure over sibling helpers (a helper-of-helper is captured
    # even if no detector imports it directly).
    captured: set[Path] = set()
    while worklist:
        helper = worklist.pop()
        if helper in captured:
            continue
        captured.add(helper)
        helper_rel = _rel_posix(helper, root)
        for name in _imported_module_names(_read_python(helper, root), helper_rel):
            nxt = _sibling_helper_path(name, abs_scripts_dir)
            if nxt is not None and nxt not in captured:
                worklist.append(nxt)

    return frozenset(p.relative_to(root).as_posix() for p in captured)


def _rel_posix(path: Path, root: Path) -> str:
    """Return *path* as a repo-relative POSIX string (or absolute if outside root)."""
    return (path.relative_to(root) if path.is_relative_to(root) else path).as_posix()


def _read_python(path: Path, root: Path) -> str:
    """Read and pre-parse a Python source for the import walk. Fail closed (G1)."""
    rel = _rel_posix(path, root)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DetectorScopeError(
            f"cannot read detector source {rel}: {exc}\n"
            "Per .claude/rules/guards.md Rule G1, unreadable detectors fail closed."
        ) from exc
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise DetectorScopeError(
            f"cannot parse detector source {rel}: {exc}\n"
            "Per .claude/rules/guards.md Rule G1, parse errors fail closed."
        ) from exc
    return source


def detector_source_scope(
    repo_root: Path | None = None,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    scripts_dir: Path = DEFAULT_SCRIPTS_DIR,
) -> frozenset[str]:
    """Return the full content-derived safety-gate scope (repo-relative POSIX).

    The union of the corpus ``detector_sources`` layer (S5U-922) and the
    import-graph helper closure (S5U-926). Fail-closed (``DetectorScopeError``)
    on any malformed corpus or unreadable/unparseable detector source. Callers
    test ``changed_path in detector_source_scope(...)`` directly.
    """
    return corpus_source_scope(repo_root, corpus_dir) | import_graph_scope(repo_root, scripts_dir)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. ``--list`` prints one in-scope path per line on stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the content-derived safety-gate scope, one path per line.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="Corpus directory (repo-relative or absolute).",
    )
    parser.add_argument(
        "--scripts-dir",
        type=Path,
        default=DEFAULT_SCRIPTS_DIR,
        help="Scripts directory for the import-graph walk (repo-relative or absolute).",
    )
    args = parser.parse_args(argv)

    try:
        scope = detector_source_scope(
            repo_root=args.repo_root.resolve(),
            corpus_dir=args.corpus_dir,
            scripts_dir=args.scripts_dir,
        )
    except DetectorScopeError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1

    if args.list:
        for path in sorted(scope):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

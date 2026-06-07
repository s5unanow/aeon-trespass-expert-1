"""Content-derived safety-gate scope: the union of corpus ``detector_sources``.

S5U-922. The safety-gate scope matchers in ``.claude/hooks/pre-pr-check.sh`` and
``scripts/check_post_merge_coordinator_ack.py`` historically matched only
``scripts/check_*.{sh,py}`` and ``scripts/pre-*.{sh,py}`` by name. S5U-920
extracted the load-bearing parametrize-detector decorator logic into the sibling
``scripts/_parametrize_ast.py`` — a leading-underscore path that matches neither
clause. A future lone edit to that file (or any of the
``scripts/_instruction_drift_rule_*.py`` helpers, which escape the same way)
would bypass the pre-PR coordinator-ack refusal and the post-merge audit.

This module closes that gap the Rule-G2 (``.claude/rules/guards.md``)
content-derived way: the in-scope set is derived from the UNION of every corpus's
``detector_sources`` list, not a hardcoded name pattern. The corpus
``detector_sources`` is already the authoritative contract for "which files carry
load-bearing detector logic" (it is what ``check_detector_corpus_coverage.py``
binds against). Deriving safety-gate scope from the same union means any future
extracted detector helper declared in a corpus is automatically in scope without
editing a regex — and benign underscore helpers (``scripts/_export_*.py`` etc.)
are NOT over-captured, which a name-pattern broadening would do.

Both safety-gate matchers consume THIS module so they cannot drift: the Python
audit imports ``detector_source_scope``; the bash hook shells out to the
``--list`` CLI. One source of truth.

## Rule G1 (fail-closed defaults)

Every degenerate corpus input raises ``DetectorScopeError`` (CLI: exits non-zero
with the message on stderr):

- A corpus ``.toml`` that does not parse (``TOMLDecodeError`` / ``OSError``).
- A corpus missing a non-empty ``detector_sources`` list.
- A ``detector_sources`` entry that is not a non-empty string.

The ONE non-raising degenerate case is an **absent** corpus directory: that means
the caller is not running against the real repo (e.g. a synthetic ``tmp_path``
unit-test repo that has no corpus), so there is no detector contract to enforce
and the extra set is empty. The real-repo callers pin ``repo_root`` to the actual
repository root, which always contains the corpus directory.

Usage (CLI, one path per line on stdout):
    python scripts/_detector_source_scope.py --list
    python scripts/_detector_source_scope.py --list --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = Path("apps/pipeline/tests/safety_gate_corpus")


class DetectorScopeError(RuntimeError):
    """Raised when a corpus file is present but malformed (Rule G1 fail-closed)."""


def detector_source_scope(
    repo_root: Path | None = None,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> frozenset[str]:
    """Return the union of every corpus's ``detector_sources`` (repo-relative).

    Fail-closed (``DetectorScopeError``) on any malformed corpus file. An absent
    corpus directory returns an empty set (see module docstring — synthetic
    test repos legitimately have no corpus). The returned paths are exactly as
    declared in the corpus TOMLs (repo-relative POSIX strings), so a caller can
    test ``changed_path in detector_source_scope(...)`` directly.
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. ``--list`` prints one in-scope path per line on stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the union of corpus detector_sources, one path per line.",
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
    args = parser.parse_args(argv)

    try:
        scope = detector_source_scope(
            repo_root=args.repo_root.resolve(), corpus_dir=args.corpus_dir
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

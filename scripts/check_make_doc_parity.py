#!/usr/bin/env python3
"""Make/doc parity check (S5U-690).

Fails CI when the `make lint` recipe in `Makefile` drifts from how it is
documented in `CLAUDE.md` and load-bearing templates.

The check is deliberately narrow: it extracts the set of *tool tokens* the
`lint` target actually invokes (e.g. ``ruff``, ``mypy``, ``lint-imports``,
``check_file_length``, ``validate_fixture_manifest``, ``check_codegen_fresh``,
``pnpm``), and checks that every token appears in:

* the ``make lint`` hash-comment in ``CLAUDE.md`` (the one-line summary under
  the ``## Commands`` block);
* the ``make lint passes`` bullet in each documented target file.

Extra descriptive tokens in the docs (``--check``, ``fixture-manifest``, etc.)
are allowed — drift is defined as a Makefile-side token whose *stem* is absent
from the documented summary.

Fail-closed on: missing Makefile, unparseable Makefile, missing CLAUDE.md,
missing/empty ``make lint`` comment, missing documented target files. All
exit non-zero with a clear message (per `.claude/rules/guards.md` Rule G1).

Usage: ``python scripts/check_make_doc_parity.py [--repo-root PATH]``
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

MAKEFILE = Path("Makefile")
CLAUDE_MD = Path("CLAUDE.md")

# Files that carry their own one-line "make lint passes (...)" summary.
# Each one must mention every Makefile-side tool token (alias-normalised).
DOCUMENTED_TARGETS: tuple[tuple[Path, re.Pattern[str]], ...] = (
    (
        Path("docs/EXTRACTION_TICKET_TEMPLATE.md"),
        re.compile(r"`make lint`\s+passes\s*\(([^)]*)\)", re.IGNORECASE),
    ),
)

# Token stems extracted from a Makefile command line — the noun we care about,
# not the invocation wrapper. For example `uv run ruff check .` carries stem
# ``ruff``; `bash scripts/check_codegen_fresh.sh` carries stem
# ``check_codegen_fresh``.
_WRAPPER_STEMS: frozenset[str] = frozenset(
    {"uv", "run", "python", "bash", "sh", "pnpm", "-r", "exec", "node"}
)


def _makefile_lint_lines(text: str) -> list[str]:
    """Return the command lines of the ``lint:`` Makefile target.

    Fails closed: raises if the target is missing.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_target = False
    for line in lines:
        if not in_target:
            if re.match(r"^lint\s*:", line):
                in_target = True
            continue
        if line and not line.startswith("\t"):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    if not out:
        raise RuntimeError("Makefile: target 'lint' missing or has no command lines.")
    return out


def _extract_stem(token: str) -> str | None:
    """Strip path / extension / flags to return the bare stem.

    Returns None for wrapper words (``uv``, ``run``, ``bash``, …) and for
    argument-looking tokens (leading ``-`` or ``.``).
    """
    if not token or token.startswith("-"):
        return None
    if token in {".", ".."}:
        return None
    # Strip leading path: `scripts/check_foo.py` -> `check_foo.py`.
    name = Path(token).name
    # Strip extension: `check_foo.py` -> `check_foo`, `foo.sh` -> `foo`.
    if "." in name:
        name = name.rsplit(".", 1)[0]
    if not name or name in _WRAPPER_STEMS:
        return None
    # `uv` wrapper stems like `run` slip through the path stripping. Guard.
    if name.lower() in _WRAPPER_STEMS:
        return None
    return name


def makefile_lint_tokens(text: str) -> set[str]:
    """Extract the set of meaningful tool stems invoked by ``make lint``.

    Fails closed: raises if the Makefile target cannot be parsed or if no
    tokens were recovered (an empty token set would silently pass the
    downstream doc-parity check).
    """
    tokens: set[str] = set()
    for line in _makefile_lint_lines(text):
        # Split on whitespace; crude but sufficient for the command shapes the
        # Makefile actually uses (no shell pipelines in `make lint`).
        parts = line.split()
        for part in parts:
            stem = _extract_stem(part)
            if stem is None:
                continue
            # First meaningful stem per command line is the tool; subsequent
            # stems (subcommand like `check`, target like `lint`, path `.`)
            # are not interesting for parity purposes.
            tokens.add(stem)
            break
    if not tokens:
        raise RuntimeError("Makefile: parsed 'lint' target but recovered zero tool stems.")
    return tokens


# Aliases: Makefile-side stem -> one or more doc-side tokens that satisfy it.
# When a doc summary mentions any alias, the Makefile-side stem is considered
# "documented". Aliases keep the check tolerant of the short-hand names docs
# use ("fixture-manifest" for validate_fixture_manifest) without requiring
# docs to echo Python-source filenames verbatim.
_DOC_ALIASES: dict[str, frozenset[str]] = {
    "validate_fixture_manifest": frozenset({"fixture-manifest", "validate-fixtures", "fixtures"}),
    "check_codegen_fresh": frozenset({"codegen", "codegen-freshness", "codegen-fresh"}),
    "check_file_length": frozenset({"file-length"}),
    "check_make_doc_parity": frozenset({"make-doc-parity", "make/doc-parity", "doc-parity"}),
    "lint-imports": frozenset({"import-linter", "import-linter,", "imports"}),
    "pnpm": frozenset({"pnpm-lint", "oxlint"}),
}


def _normalise_for_match(text: str) -> str:
    """Lowercase and collapse ``_`` / whitespace to ``-`` for fuzzy comparison."""
    return re.sub(r"[\s_]+", "-", text.lower())


def stem_is_documented(stem: str, doc_summary: str) -> bool:
    """Return True if ``stem`` (or any of its aliases) appears in ``doc_summary``.

    Matching is substring-based on a normalised representation so that
    documentation can use hyphenated short-forms.
    """
    haystack = _normalise_for_match(doc_summary)
    needles: set[str] = {_normalise_for_match(stem)}
    needles.update(_normalise_for_match(a) for a in _DOC_ALIASES.get(stem, frozenset()))
    return any(needle in haystack for needle in needles)


_CLAUDE_LINT_COMMENT_RE = re.compile(
    r"^\s*make\s+lint\s+#\s*(.+?)\s*$",
    re.MULTILINE,
)


def extract_claude_summary(text: str) -> str:
    """Extract the one-line `make lint   # ...` comment from CLAUDE.md.

    Fails closed if absent or empty.
    """
    match = _CLAUDE_LINT_COMMENT_RE.search(text)
    if match is None:
        raise RuntimeError("CLAUDE.md: could not find 'make lint # ...' summary line.")
    summary = match.group(1).strip()
    if not summary:
        raise RuntimeError("CLAUDE.md: 'make lint' comment is empty.")
    return summary


def _documented_target_summary(path: Path, pattern: re.Pattern[str]) -> str:
    """Extract the inline-bullet `make lint passes (...)` summary from a template."""
    text = path.read_text(encoding="utf-8")
    match = pattern.search(text)
    if match is None:
        raise RuntimeError(f"{path}: pattern {pattern.pattern!r} did not match.")
    summary = match.group(1).strip()
    if not summary:
        raise RuntimeError(f"{path}: matched 'make lint passes (...)' body is empty.")
    return summary


def audit(repo_root: Path) -> list[str]:
    """Run the parity audit. Return a list of drift messages; empty = clean."""
    makefile_path = repo_root / MAKEFILE
    if not makefile_path.is_file():
        raise RuntimeError(f"Makefile missing at {makefile_path}.")
    claude_path = repo_root / CLAUDE_MD
    if not claude_path.is_file():
        raise RuntimeError(f"CLAUDE.md missing at {claude_path}.")

    makefile_text = makefile_path.read_text(encoding="utf-8")
    tokens = makefile_lint_tokens(makefile_text)

    claude_summary = extract_claude_summary(claude_path.read_text(encoding="utf-8"))

    target_summaries: list[tuple[str, str]] = [
        (CLAUDE_MD.as_posix(), claude_summary),
    ]
    for rel, pattern in DOCUMENTED_TARGETS:
        path = repo_root / rel
        if not path.is_file():
            raise RuntimeError(f"Documented target missing at {path}.")
        summary = _documented_target_summary(path, pattern)
        target_summaries.append((rel.as_posix(), summary))

    drift: list[str] = []
    for target_path, summary in target_summaries:
        for stem in sorted(tokens):
            if not stem_is_documented(stem, summary):
                drift.append(
                    f"{target_path}: documented 'make lint' summary is missing "
                    f"Makefile-side tool '{stem}'. Current summary: {summary!r}"
                )
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
        help="Repo root to scan (defaults to parent of scripts/).",
    )
    args = parser.parse_args()
    try:
        drift = audit(args.repo_root.resolve())
    except RuntimeError as exc:
        print(f"check_make_doc_parity: FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    if drift:
        print("check_make_doc_parity: drift detected", file=sys.stderr)
        for msg in drift:
            print(f"  {msg}", file=sys.stderr)
        return 1
    print("check_make_doc_parity: OK (Makefile/CLAUDE.md/template summaries agree)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

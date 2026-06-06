#!/usr/bin/env python3
"""Detect added Python lines that fall inside a parametrize-equivalent context.

S5U-650: closes the gap where the previous reviewer-side line-grep missed
multiline row additions like `+        ("new_case", expected),` inside an
existing `@pytest.mark.parametrize` block — the added line carries no
decorator/call token, so the line-grep silently passed.

This helper walks each changed `.py` file's head-version AST, maps every
`+`-prefixed diff line to the enclosing `FunctionDef` / `AsyncFunctionDef` /
`ClassDef` (decorators included in the line range), and flags lines whose
enclosing context matches a documented parametrize-equivalent shape:
`@pytest.mark.parametrize` (function/class-level, stacked OK), `@mark.parametrize`
(`from pytest import mark`), bare `@parametrize` (`from pytest.mark import
parametrize`), `@given` (hypothesis), `@pytest.fixture(..., params=[...])`, and
the `pytest_generate_tests(metafunc)` body. The full case contract lives in the
`parametrize_red_before` corpus.

The detector is content-derived (.claude/rules/guards.md Rule G2): it inspects
decorator AST shape, not a hardcoded decorator-name list. S5U-920 extends this
by resolving `import ... as <alias>` renames to their canonical binding (see
`_parametrize_ast.collect_import_aliases`), so `from pytest import mark as m2;
@m2.parametrize` flags by content, not surface name. A custom user-defined
wrapper (`@my_team.parametrize`) is an acknowledged out-of-scope residual
covered by the reviewer prose-fallback.

Exit codes: 0 — none added; 1 — >=1 added (reviewer must verify red-before per
.claude/rules/hooks.md); 2 — fail-closed degenerate input (Rule G1: bad ref,
git diff failure, git show failure on a listed `.py` file).

Scope: `.py` only. Vitest `.each` (`.ts` / `.tsx`) is out of scope; the
reviewer prompt retains a line-grep fallback for those file types.

Usage:
    uv run python scripts/check_parametrize_red_before.py \\
        --base origin/main --head HEAD --json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

# Sibling helper (S5U-920). Make the scripts dir importable whether this file is
# run as a script or loaded via spec_from_file_location in the corpus harness.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _parametrize_ast import collect_import_aliases, decorator_context_label

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Match:
    file: str
    line: int
    context: str
    function: str


@dataclass(frozen=True)
class Skip:
    file: str
    reason: str


def _fail_closed(message: str) -> NoReturn:
    """Print `message` to stderr and exit 2 (Rule G1, matches docstring)."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _verify_ref_exists(ref: str) -> None:
    """Fail closed when `ref` does not resolve to a commit (Rule G1)."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail_closed(
            f"ERROR: cannot resolve ref '{ref}' to a commit.\n"
            "  This usually means the CI checkout is shallow or the ref is\n"
            "  unfetched. Set fetch-depth: 0 on actions/checkout, or pass\n"
            "  --base / --head explicitly.\n"
            f"  git rev-parse stderr: {result.stderr.strip()}"
        )


def _changed_python_files(base: str, head: str) -> list[str]:
    """Return changed `.py` files between base and head (G1 fail-closed)."""
    primary = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}", "--", "*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    if primary.returncode == 0:
        return [line.strip() for line in primary.stdout.splitlines() if line.strip()]
    fallback = subprocess.run(
        ["git", "diff", "--name-only", base, head, "--", "*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    if fallback.returncode == 0:
        return [line.strip() for line in fallback.stdout.splitlines() if line.strip()]
    _fail_closed(
        f"ERROR: git diff failed for both '{base}...{head}' and '{base} {head}'.\n"
        f"  primary stderr: {primary.stderr.strip()}\n"
        f"  fallback stderr: {fallback.stderr.strip()}"
    )


def _added_lines_for(base: str, head: str, path: str) -> list[int]:
    """Return added (head-version) line numbers for `path`."""
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...{head}", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--unified=0", base, head, "--", path],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        _fail_closed(
            f"ERROR: git diff failed for path {path!r}.\n  stderr: {result.stderr.strip()}"
        )

    added: list[int] = []
    current_head_line: int | None = None
    for raw in result.stdout.splitlines():
        m = _HUNK_HEADER_RE.match(raw)
        if m is not None:
            current_head_line = int(m.group(1))
            continue
        if current_head_line is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            added.append(current_head_line)
            current_head_line += 1
        elif raw.startswith(" "):
            current_head_line += 1
        # `-`-prefixed lines do not advance the head counter.
    return added


def _read_head_blob(head: str, path: str) -> str:
    """Return file contents at `head:path`, fail closed on git-show failure.

    Per .claude/rules/guards.md Rule G1: a `.py` path that surfaced in
    `git diff --name-only` but cannot be read at head (deleted blob,
    encoding issue, very large blob) is a degenerate input — the helper
    cannot do its job for that file. Exit non-zero with stderr rather
    than silently no-op.
    """
    result = subprocess.run(
        ["git", "show", f"{head}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail_closed(
            f"ERROR: git show failed for path {path!r} at head {head!r}.\n"
            "  This file appeared in `git diff --name-only` but its blob\n"
            "  is unreadable at head (deleted at head, encoding issue, or\n"
            "  oversized blob). Re-fetch the head ref or pass --head\n"
            "  explicitly.\n"
            f"  git show stderr: {result.stderr.strip()}"
        )
    return result.stdout


def _node_line_range(node: ast.AST) -> tuple[int, int] | None:
    """Return (start, end) line range for a def/class node, decorators included."""
    if not hasattr(node, "lineno"):
        return None
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", start)
    if start is None or end is None:
        return None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        for d in node.decorator_list:
            d_start = getattr(d, "lineno", start)
            if d_start is not None and d_start < start:
                start = d_start
    return start, end


@dataclass
class _ContextNode:
    name: str
    start: int
    end: int
    label: str | None


def _collect_contexts(tree: ast.AST) -> list[_ContextNode]:
    """Collect FunctionDef/AsyncFunctionDef/ClassDef + parametrize label."""
    aliases = collect_import_aliases(tree)
    contexts: list[_ContextNode] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        rng = _node_line_range(node)
        if rng is None:
            continue
        start, end = rng
        label: str | None = None
        for d in node.decorator_list:
            lab = decorator_context_label(d, aliases)
            if lab is not None:
                label = lab
                break
        # pytest_generate_tests body: any added line inside the function
        # body counts (data lives in the body, not in a decorator).
        if (
            label is None
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "pytest_generate_tests"
        ):
            label = "pytest_generate_tests"
        contexts.append(
            _ContextNode(name=getattr(node, "name", "<module>"), start=start, end=end, label=label)
        )
    return contexts


def _label_for_line(contexts: list[_ContextNode], line: int) -> tuple[str, str] | None:
    """Return (label, function_name) for the innermost labeled context covering `line`.

    Walks from innermost to outermost so that a class-level decorator
    label still matches when the inner def has no own label.
    """
    covering = sorted(
        (c for c in contexts if c.start <= line <= c.end),
        key=lambda c: c.end - c.start,
    )
    if not covering:
        return None
    inner_name = covering[0].name
    for c in covering:
        if c.label is not None:
            return c.label, inner_name
    return None


def analyze_file(
    path: str,
    head_source: str,
    added_lines: Iterable[int],
) -> tuple[list[Match], list[Skip]]:
    """Walk the AST and return matches + skips for this file."""
    try:
        tree = ast.parse(head_source, filename=path)
    except SyntaxError as exc:
        return [], [Skip(file=path, reason=f"syntax error: {exc.msg} at line {exc.lineno}")]

    contexts = _collect_contexts(tree)
    matches: list[Match] = []
    seen: set[tuple[str, int]] = set()
    for line in added_lines:
        labelled = _label_for_line(contexts, line)
        if labelled is None:
            continue
        label, fn_name = labelled
        key = (path, line)
        if key in seen:
            continue
        seen.add(key)
        matches.append(Match(file=path, line=line, context=label, function=fn_name))
    return matches, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect added Python lines inside parametrize-equivalent contexts (S5U-650)",
    )
    parser.add_argument("--base", default="main", help="Base ref (default: main)")
    parser.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of human-readable text",
    )
    args = parser.parse_args()

    _verify_ref_exists(args.base)
    _verify_ref_exists(args.head)

    changed = _changed_python_files(args.base, args.head)
    all_matches: list[Match] = []
    all_skips: list[Skip] = []
    for path in changed:
        added = _added_lines_for(args.base, args.head, path)
        if not added:
            continue
        head_src = _read_head_blob(args.head, path)
        matches, skips = analyze_file(path, head_src, added)
        all_matches.extend(matches)
        all_skips.extend(skips)

    payload = {
        "matches": [
            {"file": m.file, "line": m.line, "context": m.context, "function": m.function}
            for m in all_matches
        ],
        "skipped_files": [{"file": s.file, "reason": s.reason} for s in all_skips],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not all_matches and not all_skips:
            print("No parametrize-equivalent rows added.")
        for m in all_matches:
            print(f"{m.file}:{m.line} inside {m.context} (function {m.function!r})")
        for s in all_skips:
            print(f"SKIP: {s.file}: {s.reason}", file=sys.stderr)
    return 1 if all_matches else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Block per-test `maxDiffPixelRatio` overrides without a justification marker.

Implements bullet 4 of S5U-608's fix sketch (S5U-657), extended in S5U-757
to close four syntactic-variant bypasses surfaced by the post-ship review of
PR #364. Scans every Playwright-runnable spec file under `apps/web/tests/e2e/`
for `maxDiffPixelRatio` overrides and fails if any line carrying that
override does NOT have an immediately preceding
`// visual-gate-override: allow reason=<non-empty>` comment.

Per `.claude/rules/guards.md`:

- **Rule G1** (fail-closed defaults): a missing scan dir, a non-directory
  scan dir, or an unreadable spec file each exit non-zero with a clear
  message. The legitimate-override allowlist is empty (no env-var or
  workflow-`if` overrides).
- **Rule G2** (content-derived sets): the blocked set is content-derived in
  two senses. (1) The in-scope file set is computed from Playwright's
  default `testMatch` glob (`**/*.@(spec|test).?(c|m)[jt]s?(x)`), not a
  hardcoded `.spec.ts`. (2) The match set is every line that exhibits an
  ECMAScript object-literal binding of the `maxDiffPixelRatio` key —
  bare-key colon, quoted-key colon, property shorthand, or computed-key
  declaration site. The set is derived at scan time from the four
  `PropertyDefinition` productions in the language grammar (see
  `tmp/plan-s5u-757.md` §4a), not a single regex token.

Detected forms:

- Bare key:           `maxDiffPixelRatio: 0.5`
- Quoted key:         `'maxDiffPixelRatio': 0.5` / `"maxDiffPixelRatio": 0.5`
- Property shorthand: `{ maxDiffPixelRatio }` / `, maxDiffPixelRatio,`
                      (single-line or multi-line with token on its own line
                      bracketed by `,`/`}`)
- Computed key:       `const k = 'maxDiffPixelRatio'` (the declaration site;
                      the use site `{ [k]: 0.5 }` carries no token and is
                      undetectable by static regex)

Adjacency rule: walk backwards from the violation line over **blank
lines only**; the first non-blank line MUST be the justification
marker. A non-blank, non-marker line directly above the override line
(e.g. another statement, a JSDoc comment that isn't the marker) is a
violation. For multi-line `toHaveScreenshot(...)` calls, place the
marker on the line immediately preceding the override line:

```ts
await expect(content).toHaveScreenshot('foo.png', {
  // visual-gate-override: allow reason=intentional ascii-art drift
  maxDiffPixelRatio: 0.05,
});
```

Usage:
    python scripts/check_visual_test_overrides.py [SCAN_DIR] [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Content-derived match set, one regex per ECMAScript PropertyDefinition shape
# that can bind the `maxDiffPixelRatio` key (see `tmp/plan-s5u-757.md` §4a for
# the spec citation). Any one match flags the line.
#
# The rule is enforced at the line level, not the AST level. False-positive on
# a token inside a string literal that is NOT an actual override is tolerated
# (worker can move the string or add the marker comment) — see plan §4b
# "token inside string literal".
#
# (1) Bare-or-quoted key followed by colon: `maxDiffPixelRatio:`,
#     `'maxDiffPixelRatio':`, `"maxDiffPixelRatio":`. The optional `['"]?`
#     wrapping is symmetric — quoted forms must use matching quote types but a
#     line-level scan accepts either pair (the regex is line-grained, not
#     parse-tree-grained).
OVERRIDE_BARE_OR_QUOTED_RE = re.compile(r"['\"]?\bmaxDiffPixelRatio\b['\"]?\s*:")

# (2) Property shorthand: token sits adjacent to `{` or `,` (literal opening
#     or a separator), and is followed by `,` or `}` (separator or close), with
#     NO `:` or `=` after it. Two sub-forms:
#       (a) inline: `{ ..., maxDiffPixelRatio, ... }` or `{ maxDiffPixelRatio }`
#           — opener-or-comma BEFORE token, comma-or-brace AFTER token.
#       (b) multi-line: token alone on its own line indented under a `{`,
#           bracketed by trailing `,` or `}`.
#     The negative-followed-by clause `(?![:=\w])` keeps `maxDiffPixelRatioFoo`
#     and `maxDiffPixelRatio: 0.5` (the bare-key form, already covered by (1))
#     out of this branch.
OVERRIDE_SHORTHAND_INLINE_RE = re.compile(r"[\{,]\s*maxDiffPixelRatio\s*(?![:=\w])\s*[,}]")
OVERRIDE_SHORTHAND_MULTILINE_RE = re.compile(r"^\s*maxDiffPixelRatio\s*(?![:=\w])\s*[,}]")

# (3) Computed-key declaration site: `const k = 'maxDiffPixelRatio'` (or `let`
#     / `var`). The use site `{ [k]: V }` carries no token, so a static
#     detector must anchor on the binding. Closing-quote-immediately-after
#     anchor (`['"]maxDiffPixelRatio['"]`) prevents false positives on prose
#     strings that contain but are not equal to the token (see plan §4d).
OVERRIDE_COMPUTED_DECL_RE = re.compile(
    r"\b(?:const|let|var)\s+\w+\s*=\s*['\"]maxDiffPixelRatio['\"]"
)

# Tuple driving the per-line scan. Order is informational only; any-match
# wins.
OVERRIDE_REGEXES: tuple[re.Pattern[str], ...] = (
    OVERRIDE_BARE_OR_QUOTED_RE,
    OVERRIDE_SHORTHAND_INLINE_RE,
    OVERRIDE_SHORTHAND_MULTILINE_RE,
    OVERRIDE_COMPUTED_DECL_RE,
)


def _line_has_override(line: str) -> bool:
    """Return True iff `line` matches any of the four override-shape regexes."""
    return any(rx.search(line) for rx in OVERRIDE_REGEXES)


# Playwright's default `testMatch` is `**/*.@(spec|test).?(c|m)[jt]s?(x)`, which
# expands to twelve concrete extensions. The scanner enumerates the same set so
# a renamed-extension bypass (the S5U-757 item-4 vector) is closed.
SPEC_EXTENSIONS: tuple[str, ...] = (
    "spec.ts",
    "spec.tsx",
    "spec.js",
    "spec.jsx",
    "spec.mjs",
    "spec.cjs",
    "test.ts",
    "test.tsx",
    "test.js",
    "test.jsx",
    "test.mjs",
    "test.cjs",
)

# Justification marker: comment line shaped exactly like
# `// visual-gate-override: allow reason=<non-empty>`. The `\S.*` clause
# requires at least one non-whitespace character immediately after `reason=`,
# blocking empty- and whitespace-only reasons (S5U-591 LOOSEN-THRESHOLD
# parity).
MARKER_RE = re.compile(
    r"//\s*visual-gate-override\s*:\s*allow\s+reason=(?P<reason>\S.*?)\s*$",
)


@dataclass(frozen=True)
class Violation:
    """A single forbidden-flag hit."""

    path: str
    line: int
    excerpt: str
    reason: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}: {self.excerpt.strip()!r}"


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _walk_back_to_first_nonblank(lines: list[str], idx: int) -> int | None:
    """Return the index of the first non-blank line strictly above `idx`.

    Blank lines (whitespace-only) are skipped. Returns None if the walk
    runs off the top of the file.
    """
    j = idx - 1
    while j >= 0 and lines[j].strip() == "":
        j -= 1
    return j if j >= 0 else None


def _is_marker_line(line: str) -> bool:
    """Return True iff `line` is a valid `visual-gate-override` marker.

    The marker grammar is strict: `// visual-gate-override: allow reason=<non-empty>`.
    Whitespace tolerance: any indentation, any whitespace around `:`, ` `, and the
    `reason=` separator. Non-empty reason is enforced by the regex's `\\S.*` clause.
    """
    return MARKER_RE.search(line) is not None


def _scan_spec_file(path: Path, repo_root: Path) -> list[Violation]:
    """Scan one spec file for unjustified `maxDiffPixelRatio` overrides.

    Fails closed (raises) on read error — propagated to the caller so the
    overall scan exits non-zero with a clear message (Rule G1).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc

    lines = text.splitlines()
    rel = _rel(path, repo_root)
    violations: list[Violation] = []
    for i, line in enumerate(lines):
        if not _line_has_override(line):
            continue
        # The override line itself, if it ALSO carries the marker on the
        # same line (rare but legitimate — `// visual-gate-override: allow
        # reason=foo\n  maxDiffPixelRatio: 0.5,` is the canonical form, but
        # `maxDiffPixelRatio: 0.5, // visual-gate-override: allow reason=foo`
        # is also reasonable), passes immediately.
        if _is_marker_line(line):
            continue
        prior_idx = _walk_back_to_first_nonblank(lines, i)
        if prior_idx is None:
            violations.append(
                Violation(
                    path=rel,
                    line=i + 1,
                    excerpt=line,
                    reason="override-without-justification (no preceding line)",
                )
            )
            continue
        prior = lines[prior_idx]
        if not _is_marker_line(prior):
            violations.append(
                Violation(
                    path=rel,
                    line=i + 1,
                    excerpt=line,
                    reason=(
                        "override-without-justification "
                        f"(preceding non-blank line {prior_idx + 1} is not a "
                        "`// visual-gate-override: allow reason=<non-empty>` marker)"
                    ),
                )
            )
    return violations


def _iter_spec_files(scan_dir: Path) -> list[Path]:
    """Return every Playwright-runnable spec file under `scan_dir`, sorted.

    The set of in-scope extensions is derived from Playwright's default
    `testMatch` glob (`**/*.@(spec|test).?(c|m)[jt]s?(x)`); see plan §4a.
    Deduped via a `set` because `rglob` is per-extension and a file cannot
    legitimately match two of these extensions, but the set protects against
    accidental overlap.
    """
    seen: set[Path] = set()
    for ext in SPEC_EXTENSIONS:
        for path in scan_dir.rglob(f"*.{ext}"):
            seen.add(path)
    return sorted(seen)


def scan(scan_dir: Path, repo_root: Path) -> list[Violation]:
    """Scan all spec files under `scan_dir`. Raise RuntimeError on G1 failures.

    Empty file list returns []; the caller (main) handles the "no specs found"
    warn-and-pass case.
    """
    if not scan_dir.exists():
        raise RuntimeError(f"scan dir {scan_dir} does not exist")
    if not scan_dir.is_dir():
        raise RuntimeError(f"scan dir {scan_dir} is not a directory")
    spec_files = _iter_spec_files(scan_dir)
    violations: list[Violation] = []
    for path in spec_files:
        violations.extend(_scan_spec_file(path, repo_root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan Playwright spec files for per-test `maxDiffPixelRatio` "
            "overrides without an adjacent `// visual-gate-override: allow "
            "reason=<...>` justification comment. Implements bullet 4 of "
            "S5U-608's fix sketch (S5U-657)."
        )
    )
    parser.add_argument(
        "scan_dir",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Directory to scan for Playwright spec files (`*.{spec,test}.{ts,tsx,"
            "js,jsx,mjs,cjs}`). Defaults to <repo_root>/apps/web/tests/e2e."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of scripts/).",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    if not repo_root.exists():
        print(
            f"::error::visual-test-overrides: repo root {repo_root} does not exist",
            file=sys.stderr,
        )
        return 1

    scan_dir: Path = (
        args.scan_dir if args.scan_dir is not None else repo_root / "apps" / "web" / "tests" / "e2e"
    )

    try:
        violations = scan(scan_dir, repo_root)
    except RuntimeError as exc:
        print(f"::error::visual-test-overrides: {exc}", file=sys.stderr)
        return 1

    spec_files = _iter_spec_files(scan_dir)
    if not spec_files:
        # G1 deviation (documented in plan §4a): empty file list returns 0
        # with a stdout warning. A fresh scaffold legitimately has zero
        # specs; we trade a small G1 strictness for usability. Any future
        # bypass attempt that *removes* spec files would be visible in the
        # PR diff and is outside this guard's scope.
        print(
            "visual-test-overrides: no spec files (`*.{spec,test}.{ts,tsx,js,jsx,"
            f"mjs,cjs}}`) found under {scan_dir}; nothing to scan."
        )
        return 0

    if violations:
        print(
            "::error::visual-test-overrides: per-test `maxDiffPixelRatio` "
            "override(s) without a justification marker. The central threshold "
            "in `apps/web/playwright.config.ts` is authoritative; per-test "
            "overrides bypass it. To allow an override, add a comment "
            "`// visual-gate-override: allow reason=<why>` on the line "
            "immediately preceding the override (blank lines may separate). "
            "Violations:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v.format()}", file=sys.stderr)
        return 1

    print(
        f"visual-test-overrides: clean ({len(spec_files)} spec file(s) scanned under {scan_dir})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

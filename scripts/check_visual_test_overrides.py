#!/usr/bin/env python3
"""Block per-test `maxDiffPixelRatio` overrides without a justification marker.

S5U-657 (bullet 4 of S5U-608); extended S5U-757 / S5U-759. **Reworked
S5U-789** from a binding-shape regex enumeration into a token-anchored
*semantic* detector backed by a named adversarial corpus
(`apps/pipeline/tests/safety_gate_corpus/maxdiffpixelratio.toml`). Scans
every Playwright-runnable spec file under `apps/web/tests/e2e/` and fails if
any line carrying a `maxDiffPixelRatio` override does NOT have an
immediately preceding `// visual-gate-override: allow reason=<non-empty>`
comment.

Per `.claude/rules/guards.md`:

- **Rule G1** (fail-closed defaults): missing scan dir / non-directory /
  unreadable spec file each exit non-zero. No env-var or workflow-`if`
  overrides.
- **Rule G2** (content-derived sets): the in-scope file set is computed from
  Playwright's default `testMatch` glob, not a hardcoded `.spec.ts`.

Semantic shift (S5U-789): the override fires at runtime whenever the
`maxDiffPixelRatio` key reaches the screenshot options — and in *every*
binding shape the post-merge follow-ups found (S5U-760 `Map.set`, S5U-761
tagged-template, S5U-762 reassignment, S5U-763 function default-param,
S5U-764 computed-property assignment), the token appears as a **contiguous
string literal**. So the detector anchors on the token-as-string-literal
(`OVERRIDE_STRING_LITERAL_RE`) independent of the binding mechanism, instead
of enumerating one regex per binding shape. This collapses the prior
declaration/inline-computed-key/array-literal regexes into one pattern that
also closes any future binding shape that wraps the token in a string.
The two *unquoted* object-literal forms (bare key, shorthand) keep their own
patterns because there is no delimiter to anchor on.

The named corpus is the contract: reviewer-found syntactic bypasses are
added to it as `block` cases (not patched in as new regexes), and the
detector implementation must satisfy it. A future `tree-sitter-typescript`
AST detector is a documented option gated behind the same corpus.

Accepted residual CLASS — runtime string assembly/manipulation (S5U-789;
recorded as `known_residual` in the corpus, AST closure documented under
S5U-823): any construction where the **runtime override key is not statically
equal to a contiguous, delimiter-adjacent ``'maxDiffPixelRatio'`` literal**
escapes a line scanner. The boundary is NOT "the token never appears
contiguously" — in the slice/substring/replace siblings the token DOES appear
contiguously, just padded away from the delimiter; the padding is stripped at
runtime. What unites the class is that the resolved key cannot be read off the
line without evaluating a runtime string op:

- **Concatenation**: ``const k = `${prefix}PixelRatio`;`` (token never contiguous).
- **Slice / substring**: ``'_maxDiffPixelRatio_'.slice(1, -1)`` /
  ``'zmaxDiffPixelRatioz'.substring(1, 18)`` (padded literal).
- **Replace / char-code**: ``'maxDiffPixelRatioPADDING'.replace('PADDING', '')``.

S5U-823 evaluated and rejected a regex tightening: a "token as a substring of
any string literal" widening false-positives on legitimately-distinct string
keys (``'maxDiffPixelRatioFoo'``) and on error/URL/doc strings mentioning the
token, so it cannot separate the bypass from the `allow` cases — see
``tmp/plan-s5u-823.md`` §4a. Closing the class needs AST/dataflow; a line
scanner cannot follow runtime string ops. The detector therefore closes only
binding shapes that pass the **exact** token as a contiguous, delimiter-adjacent
quote-delimited literal, regardless of how it is then bound.

(The S5U-759 "multi-line array-literal" residual is now *closed*: the token
still appears as a contiguous string literal on its own line, which
`OVERRIDE_STRING_LITERAL_RE` matches.)

FP tradeoff (intentional, S5U-789): the token-anchored detector flags any
line containing the literal string `"maxDiffPixelRatio"` even when it is not
an override (e.g. asserting on the key name). This trades the old
"low-FP-but-misses-new-shapes" behavior for "catches all binding shapes; FP
is marker-resolvable." Consistent with the long-standing philosophy below
that a string-literal FP is tolerated (move the string or add the marker).

Adjacency rule: walk backwards from the violation line over blank lines
only; the first non-blank line MUST be the justification marker. The
canonical multi-line form places the marker directly above the override:

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

# Token-anchored semantic detector (S5U-789). The override fires whenever the
# `maxDiffPixelRatio` key reaches the screenshot options; the binding mechanism
# is irrelevant. Three patterns express the policy:
#
# The rule is enforced at the line level, not the AST level. False-positive on
# a token inside a string literal that is NOT an actual override is tolerated
# (worker can move the string or add the marker comment) — see the module
# docstring "FP tradeoff".
#
# (P1) Token as a contiguous STRING LITERAL in any delimiter:
#      `'maxDiffPixelRatio'`, `"maxDiffPixelRatio"`, `` `maxDiffPixelRatio` ``.
#      The backreference `\1` requires a *matching* opening/closing delimiter
#      pair. This single pattern subsumes the former computed-key declaration,
#      inline-computed-key, and array-literal regexes AND closes every binding
#      shape the post-merge follow-ups found, because in each one the token
#      appears wrapped in a string literal regardless of how it is then bound:
#        - S5U-760  `m.set('maxDiffPixelRatio', 0.5)`
#        - S5U-761  ``String.raw`maxDiffPixelRatio` ``
#        - S5U-762  ``k = `maxDiffPixelRatio` ``
#        - S5U-763  `function f(k = 'maxDiffPixelRatio')`
#        - S5U-764  `opts['maxDiffPixelRatio'] = 0.5`
#      It also closes the former S5U-759 multi-line-array residual: the token
#      still appears contiguously on its own line. The accepted residual is the
#      runtime string-assembly/manipulation CLASS — concatenation, slice,
#      substring, replace, char-code — where the runtime key is not statically
#      equal to a contiguous *delimiter-adjacent* literal (in slice/substring/
#      replace the token IS contiguous, just padded away from the delimiter).
#      Recorded as `known_residual`; AST closure and the rejected regex-widening
#      analysis are documented in the module docstring (S5U-823).
OVERRIDE_STRING_LITERAL_RE = re.compile(r"(['\"\x60])maxDiffPixelRatio\1")

# (P2) Bare (UNQUOTED) object-literal key followed by a colon:
#      `maxDiffPixelRatio:`. The quoted-key forms `'maxDiffPixelRatio':` /
#      `"maxDiffPixelRatio":` are already covered by P1; the optional `['"]?`
#      wrapping is retained only so this single pattern still matches both.
OVERRIDE_BARE_OR_QUOTED_RE = re.compile(r"['\"]?\bmaxDiffPixelRatio\b['\"]?\s*:")

# (P3) Property shorthand: token sits adjacent to `{` or `,` (literal opening
#      or a separator), and is followed by `,` or `}` (separator or close),
#      with NO `:` or `=` after it. Two sub-forms:
#        (a) inline: `{ ..., maxDiffPixelRatio, ... }` or `{ maxDiffPixelRatio }`
#            — opener-or-comma BEFORE token, comma-or-brace AFTER token.
#        (b) multi-line: token alone on its own line indented under a `{`,
#            bracketed by trailing `,` or `}`.
#      The negative-followed-by clause `(?![:=\w])` keeps `maxDiffPixelRatioFoo`
#      and the bare-key form (already covered by P2) out of this branch.
OVERRIDE_SHORTHAND_INLINE_RE = re.compile(r"[\{,]\s*maxDiffPixelRatio\s*(?![:=\w])\s*[,}]")
OVERRIDE_SHORTHAND_MULTILINE_RE = re.compile(r"^\s*maxDiffPixelRatio\s*(?![:=\w])\s*[,}]")

# Tuple driving the per-line scan. Order is informational only; any-match
# wins (violations are counted per line, not per match).
OVERRIDE_REGEXES: tuple[re.Pattern[str], ...] = (
    OVERRIDE_STRING_LITERAL_RE,
    OVERRIDE_BARE_OR_QUOTED_RE,
    OVERRIDE_SHORTHAND_INLINE_RE,
    OVERRIDE_SHORTHAND_MULTILINE_RE,
)


def _line_has_override(line: str) -> bool:
    """Return True iff `line` matches any override-shape pattern (P1-P3)."""
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

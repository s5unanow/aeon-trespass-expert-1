#!/usr/bin/env python3
"""Block per-test `maxDiffPixelRatio` overrides without a justification marker.

Implements bullet 4 of S5U-608's fix sketch (S5U-657). Scans
`apps/web/tests/e2e/**/*.spec.ts` for `maxDiffPixelRatio` overrides and
fails if any line carrying that token does NOT have an immediately
preceding `// visual-gate-override: allow reason=<non-empty>` comment.

Per `.claude/rules/guards.md`:

- **Rule G1** (fail-closed defaults): a missing scan dir, a non-directory
  scan dir, or an unreadable spec file each exit non-zero with a clear
  message. The legitimate-override allowlist is empty (no env-var or
  workflow-`if` overrides).
- **Rule G2** (content-derived sets): the blocked set is "every line
  whose body contains `maxDiffPixelRatio:` in any spec file under the
  scan dir" — derived at scan time from file contents, not from a
  hardcoded list of file or test names.

Adjacency rule: walk backwards from the violation line over **blank
lines only**; the first non-blank line MUST be the justification
marker. A non-blank, non-marker line directly above the override line
(e.g. another statement, a JSDoc comment that isn't the marker) is a
violation. For multi-line `toHaveScreenshot(...)` calls, place the
marker on the line immediately preceding the `maxDiffPixelRatio:`
line:

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

# Content-derived match: any non-string declaration of `maxDiffPixelRatio:`
# inside a spec file. We match the *line* containing the token; the rule is
# enforced at the line level, not the AST level. False-positive on a token
# inside a string literal is tolerated (worker can move the string or add
# the marker comment) — see plan §4b "token inside string literal".
OVERRIDE_TOKEN_RE = re.compile(r"\bmaxDiffPixelRatio\s*:")

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
    """Scan one `.spec.ts` file for unjustified `maxDiffPixelRatio` overrides.

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
        if not OVERRIDE_TOKEN_RE.search(line):
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
    """Return every `*.spec.ts` under `scan_dir`, sorted for stable output."""
    return sorted(scan_dir.rglob("*.spec.ts"))


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
            "Directory to scan for `*.spec.ts` files. Defaults to <repo_root>/apps/web/tests/e2e."
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
            f"visual-test-overrides: no `*.spec.ts` files found under {scan_dir}; nothing to scan."
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

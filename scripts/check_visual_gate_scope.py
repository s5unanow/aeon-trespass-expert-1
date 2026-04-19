#!/usr/bin/env python3
"""Block CI paths that would bypass the visual-regression baseline gate.

See S5U-608 for the original four-vector threat model and S5U-611 for the
Gap 1/2/3 follow-up hardening (allow-marker path allowlist, bare-pnpm
shortcut closure, shell-guard workflow YAML coverage).

Scans:
- every YAML under `.github/workflows/` and `.github/actions/` as plain
  text (catches `run:` strings, `env:` values, composite actions, quoted
  wrappers, any future workflow file);
- every `scripts` entry in `apps/web/package.json`.

Forbidden token regex (word-boundary bounded):
    (^|[\\s"'`])(-u|--update-snapshots|--ignore-snapshots)([\\s=]|$)

Exit 0 if clean, 1 on any violation. Fail-closed on unexpected errors.

Usage:
    python scripts/check_visual_gate_scope.py [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_TOKEN_RE = re.compile(
    r"""(^|[\s"'`])(-u|--update-snapshots|--ignore-snapshots)([\s="'`]|$)""",
)

# `ALLOW_MARKER` is the legacy escape hatch used by gate infrastructure
# scripts (this scanner, the shell guard) when their source text must
# mention the forbidden flag tokens literally. The scanner walks ONLY
# `.github/**` YAML files (see `GITHUB_SCAN_SUBDIRS`), never the Python /
# bash source files that contain legitimate references — so in practice
# the marker's only job inside scanned content would be to silence a real
# violation.
#
# S5U-611 hardening: any appearance of `ALLOW_MARKER` inside a scanned
# workflow/action YAML is itself a violation
# (`allow-marker-not-permitted`), regardless of whether the rest of the
# line carries a forbidden flag. That closes Gap 2 (unrestricted
# single-PR bypass). The `ALLOW_MARKER_PATHS` allowlist below names the
# small set of files that are permitted to contain the literal string; it
# exists to make the policy explicit and to fail closed if the scanner is
# ever repointed at a wider path tree.
ALLOW_MARKER = "# visual-gate-scope: allow"
ALLOW_MARKER_PATHS: frozenset[str] = frozenset(
    {
        "scripts/check_visual_gate_scope.py",
        "scripts/check_test_e2e_flags.sh",
        "apps/pipeline/tests/unit/test_check_visual_gate_scope.py",
    }
)

# Files/dirs this scanner covers. The whole `.github/` subtree is searched
# to catch composite actions and any future workflow file.
GITHUB_SCAN_SUBDIRS = (".github/workflows", ".github/actions")
GITHUB_YAML_SUFFIXES = (".yml", ".yaml")

# Scripts in `apps/web/package.json` that are the intentional local
# baseline-update path. They may exist (devs run them locally), but no
# workflow may invoke them.
LOCAL_ONLY_SCRIPTS = frozenset(
    {
        "test:visual:update",
    }
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


def _contains_forbidden_flag(text: str) -> bool:
    """Return True if `text` contains a forbidden Playwright flag token."""
    return FORBIDDEN_TOKEN_RE.search(text) is not None


def _iter_github_files(repo_root: Path) -> list[Path]:
    """Return every YAML file under `.github/workflows` and `.github/actions`."""
    results: list[Path] = []
    for subdir in GITHUB_SCAN_SUBDIRS:
        base = repo_root / subdir
        if not base.exists():
            continue
        for ext in GITHUB_YAML_SUFFIXES:
            results.extend(sorted(base.rglob(f"*{ext}")))
    return results


def _scan_github_file(path: Path, repo_root: Path) -> list[Violation]:
    """Line-scan a workflow/action YAML for forbidden flag tokens."""
    violations: list[Violation] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        # Fail closed: unreadable workflow file is a gate failure.
        return [
            Violation(
                path=_rel(path, repo_root),
                line=0,
                excerpt=f"<unreadable: {exc}>",
                reason="workflow-file-read-error",
            )
        ]
    rel = _rel(path, repo_root)
    marker_permitted = rel in ALLOW_MARKER_PATHS
    for i, line in enumerate(text.splitlines(), start=1):
        has_marker = ALLOW_MARKER in line
        if has_marker and not marker_permitted:
            # S5U-611 Gap 2: the marker is not a valid exemption anywhere
            # inside `.github/**` YAML. Emit a dedicated violation so the
            # adversarial scenario ("plant marker now, reintroduce flag
            # later") cannot establish a silent baseline.
            violations.append(
                Violation(
                    path=rel,
                    line=i,
                    excerpt=line,
                    reason="allow-marker-not-permitted",
                )
            )
            # Do NOT `continue`: we still want the forbidden-flag scan to
            # surface its own violation on the same line, so reviewers see
            # both issues at once.
        if _contains_forbidden_flag(line):
            # If the marker is present AND permitted (would never happen
            # inside `.github/**`, but retained for defence in depth), skip.
            if has_marker and marker_permitted:
                continue
            violations.append(
                Violation(
                    path=rel,
                    line=i,
                    excerpt=line,
                    reason="workflow-contains-forbidden-flag",
                )
            )
    return violations


def _load_package_json(path: Path) -> dict[str, object]:
    """Read and decode `apps/web/package.json`. Fail closed on parse error."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{path}: expected top-level JSON object")
    return loaded


def _scan_package_json(
    package_json: Path,
    repo_root: Path,
) -> tuple[list[Violation], dict[str, str]]:
    """Scan package.json scripts. Return (violations, scripts_map).

    `test:e2e` is the only script CI invokes directly; if it contains a
    forbidden flag that is a blocking violation. Any *other* script that
    contains a forbidden flag (e.g. `test:visual:update`) is allowed to
    exist — but no workflow may invoke it (enforced separately).
    """
    violations: list[Violation] = []
    pkg = _load_package_json(package_json)
    rel = _rel(package_json, repo_root)
    scripts_obj = pkg.get("scripts", {})
    if not isinstance(scripts_obj, dict):
        return (
            [
                Violation(
                    path=rel,
                    line=0,
                    excerpt=repr(scripts_obj),
                    reason="package-json-scripts-not-object",
                )
            ],
            {},
        )
    scripts: dict[str, str] = {}
    for name, cmd in scripts_obj.items():
        if isinstance(name, str) and isinstance(cmd, str):
            scripts[name] = cmd
    if "test:e2e" in scripts and _contains_forbidden_flag(scripts["test:e2e"]):
        violations.append(
            Violation(
                path=rel,
                line=0,
                excerpt=f'"test:e2e": "{scripts["test:e2e"]}"',
                reason="test-e2e-contains-forbidden-flag",
            )
        )
    return violations, scripts


# Patterns for "this workflow line invokes a package.json script by name".
# Canonical forms:
#   pnpm run <name>
#   pnpm -r run <name> / pnpm --recursive run <name>
#   pnpm --filter <pkg> run <name> / pnpm -F <pkg> run <name>
#   npm run <name> / npm run-script <name>
#   yarn run <name>
# Bare `yarn <name>` is ambiguous and not matched.
_SCRIPT_REF_RE = re.compile(
    r"""(?:pnpm|npm|yarn)
        (?:\s+
          (?:-r|--recursive|--filter(?:=\S+)?|-F|\S+)
        )*?
        \s+(?:run|run-script)\s+
        (?P<name>[A-Za-z0-9_:@./-]+)""",
    re.VERBOSE,
)


def _extract_script_names(run_text: str) -> set[str]:
    """Return the set of package.json script names referenced by `run_text`."""
    return {m.group("name") for m in _SCRIPT_REF_RE.finditer(run_text)}


def _local_only_token_patterns() -> dict[str, re.Pattern[str]]:
    """Compile a word-boundary regex for each LOCAL_ONLY_SCRIPTS entry.

    S5U-611 Gap 3: `_SCRIPT_REF_RE` requires the canonical
    `(pnpm|npm|yarn) (run|run-script) <name>` form, which misses pnpm's
    bare shortcut (`pnpm <name>` / `pnpm --filter <pkg> <name>`). The
    simplest bypass-resistant closure (per the issue's "OR" fix sketch)
    is: reject any workflow line that names a local-only script as a
    word-bounded token, regardless of surrounding syntax. The only
    legitimate references to these names live in the scanner's own source
    (this file) and comments/docs outside `.github/**`, none of which
    are scanned.
    """
    patterns: dict[str, re.Pattern[str]] = {}
    for name in LOCAL_ONLY_SCRIPTS:
        # Bound by non-identifier chars so `test-visual-update-lib` (hyphens)
        # does not match `test:visual:update` (colons) and vice versa.
        patterns[name] = re.compile(
            r"""(^|[\s"'`])""" + re.escape(name) + r"""([\s"'`]|$)""",
        )
    return patterns


def _scan_workflow_script_refs(
    workflow_files: list[Path],
    scripts: dict[str, str],
    repo_root: Path,
) -> list[Violation]:
    """Block workflow `run:` lines that invoke a forbidden or local-only script.

    Two layers:

    1. Canonical form (`pnpm run <name>`, `npm run-script <name>`, …) for
       *tainted* scripts (any package.json script whose resolved command
       contains a forbidden flag). This is the original S5U-608 check.
    2. Word-bounded name match for *local-only* scripts, independent of
       syntax — closes the bare-`pnpm <name>` shortcut (Gap 3) and any
       other surface that names the script.
    """
    violations: list[Violation] = []
    tainted = frozenset(name for name, cmd in scripts.items() if _contains_forbidden_flag(cmd))
    local_only_patterns = _local_only_token_patterns()
    if not tainted and not local_only_patterns:
        return violations
    for path in workflow_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue  # already reported by _scan_github_file
        rel = _rel(path, repo_root)
        # Marker handling identical to `_scan_github_file`: the marker is
        # not a valid exemption inside `.github/**`. We do not skip the
        # line on its basis.
        for i, line in enumerate(text.splitlines(), start=1):
            # Layer 1: canonical `(pnpm|npm|yarn) run <name>` referencing a
            # tainted script (S5U-608).
            if tainted:
                canonical_hits = _extract_script_names(line) & tainted
                if canonical_hits:
                    names = ", ".join(sorted(canonical_hits))
                    violations.append(
                        Violation(
                            path=rel,
                            line=i,
                            excerpt=line,
                            reason=f"workflow-invokes-tainted-script ({names})",
                        )
                    )
            # Layer 2: bare name appears on the line — local-only scripts.
            local_only_hits = sorted(
                name for name, pat in local_only_patterns.items() if pat.search(line)
            )
            if local_only_hits:
                names = ", ".join(local_only_hits)
                violations.append(
                    Violation(
                        path=rel,
                        line=i,
                        excerpt=line,
                        reason=f"workflow-invokes-local-only-script ({names})",
                    )
                )
    return violations


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def scan(repo_root: Path) -> list[Violation]:
    """Run all scans. Return the combined list of violations."""
    violations: list[Violation] = []
    workflow_files = _iter_github_files(repo_root)
    for path in workflow_files:
        violations.extend(_scan_github_file(path, repo_root))

    package_json = repo_root / "apps" / "web" / "package.json"
    if package_json.exists():
        pkg_violations, scripts = _scan_package_json(package_json, repo_root)
        violations.extend(pkg_violations)
        violations.extend(_scan_workflow_script_refs(workflow_files, scripts, repo_root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan CI workflows and package.json for Playwright flags that "
            "would bypass the visual-regression baseline gate."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of scripts/).",
    )
    args = parser.parse_args(argv)

    try:
        violations = scan(args.repo_root)
    except RuntimeError as exc:
        print(f"::error::visual-gate-scope scanner failed: {exc}")
        return 1

    if violations:
        print(
            "::error::visual-gate-scope: detected Playwright update/ignore "
            "flag in a CI-reachable location. Remove the flag and refresh "
            "baselines locally via `pnpm --filter @atr/web run "
            "test:visual:update`. Violations:",
        )
        for v in violations:
            print(f"  {v.format()}")
        return 1

    print("visual-gate-scope: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

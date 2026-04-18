#!/usr/bin/env python3
"""Block CI paths that would bypass the visual-regression baseline gate.

Background (see S5U-608): the original guard only inspected
`apps/web/package.json` `scripts['test:e2e']` and grepped literally for
`--update-snapshots`. Multiple minimum-diff edits bypassed it:

1. Short flag `-u` (Playwright's documented short form of update-snapshots).
2. `--ignore-snapshots` (skips screenshot assertions entirely).
3. Flags passed at the workflow `run:` line (e.g. `test:e2e -- -u`),
   leaving `package.json` untouched.
4. New workflows or jobs that invoke Playwright directly (e.g.
   `pnpm exec playwright test --update-snapshots`) and never touch
   `visual-regression.yml`.

This scanner widens both the pattern and the scope:

- It scans every YAML under `.github/workflows/` and `.github/actions/`
  as plain text, so it catches flags embedded in `run:` strings, `env:`
  values, composite actions, quoted wrappers, and any future workflow
  file anywhere in the repo.
- It scans every `scripts` entry in `apps/web/package.json`, not just
  `test:e2e`.
- It forbids workflow `run:` lines that invoke any package.json script
  whose resolved command contains a forbidden flag, and any workflow
  reference to a local-only update script by name.

Forbidden token regex (word-boundary bounded):
    (^|[\\s"'`])(-u|--update-snapshots|--ignore-snapshots)([\\s=]|$)

Lines that legitimately need to reference the forbidden tokens (this
scanner's own error messages, defense-in-depth guards in CI shell scripts)
can opt out by appending `# visual-gate-scope: allow` on the same line
in workflow YAMLs. This is intentionally visible in diff review.

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

# Escape hatch for legitimate references inside gate infrastructure. The
# marker must appear literally on the same line to take effect.
ALLOW_MARKER = "# visual-gate-scope: allow"

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
    for i, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        if _contains_forbidden_flag(line):
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


def _scan_workflow_script_refs(
    workflow_files: list[Path],
    scripts: dict[str, str],
    repo_root: Path,
) -> list[Violation]:
    """Block workflow `run:` lines that invoke a forbidden or local-only script."""
    violations: list[Violation] = []
    tainted = frozenset(name for name, cmd in scripts.items() if _contains_forbidden_flag(cmd))
    forbidden_script_names = tainted | LOCAL_ONLY_SCRIPTS
    if not forbidden_script_names:
        return violations
    for path in workflow_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue  # already reported by _scan_github_file
        rel = _rel(path, repo_root)
        for i, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            hit = _extract_script_names(line) & forbidden_script_names
            if hit:
                names = ", ".join(sorted(hit))
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

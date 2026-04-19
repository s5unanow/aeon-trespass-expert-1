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

# `ALLOW_MARKER` is the legacy escape hatch used by this scanner and the
# shell guard when their source text must mention forbidden tokens
# literally. S5U-611: any appearance of the marker inside scanned YAML
# is itself a violation (`allow-marker-not-permitted`), regardless of
# whether the rest of the line carries a forbidden flag — closes the
# unrestricted single-PR bypass (Gap 2). `ALLOW_MARKER_PATHS` names the
# fixed set of files permitted to contain the literal string.
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

# S5U-637: fixed allowlist of package.json script *names* permitted to
# carry a forbidden Playwright flag in their body. `test:e2e` is NOT in
# this allowlist — it has its own stricter rule (must be fully clean).
# Any OTHER script carrying a forbidden flag produces
# `package-json-introduces-tainted-script`, turning the rename-bypass
# from S5U-611 into a reviewer-visible diff failure at package.json
# scan time, on top of the primary workflow-side closure in
# `_scan_workflow_script_refs`.
ALLOWED_TAINTED_SCRIPTS: frozenset[str] = frozenset({"test:visual:update"})


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
            # S5U-611 Gap 2: marker never valid in scanned YAML. Do NOT
            # `continue` — still run the forbidden-flag check below so
            # reviewers see both issues at once if applicable.
            violations.append(
                Violation(path=rel, line=i, excerpt=line, reason="allow-marker-not-permitted")
            )
        if _contains_forbidden_flag(line):
            if has_marker and marker_permitted:
                continue  # defense in depth; permitted paths are outside scanned tree
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
    """Scan package.json scripts; return (violations, scripts_map).

    `test:e2e` must be fully clean (blocking if tainted). Any other
    script carrying a forbidden flag must be in `ALLOWED_TAINTED_SCRIPTS`
    or it is itself a violation (S5U-637).
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
    # S5U-637 secondary fix: any tainted script name outside
    # `ALLOWED_TAINTED_SCRIPTS` (and not `test:e2e`, handled above with
    # a stricter rule) is itself a violation, turning the S5U-611
    # rename bypass into a reviewer-visible package.json diff failure.
    for name, cmd in scripts.items():
        if name == "test:e2e" or name in ALLOWED_TAINTED_SCRIPTS:
            continue
        if _contains_forbidden_flag(cmd):
            violations.append(
                Violation(
                    path=rel,
                    line=0,
                    excerpt=f'"{name}": "{cmd}"',
                    reason=f"package-json-introduces-tainted-script ({name})",
                )
            )
    return violations, scripts


# Canonical forms matched: `pnpm run <name>`, `pnpm [-r|-F|--filter
# <pkg>] run <name>`, `npm run[-script] <name>`, `yarn run <name>`.
# Bare `pnpm <name>` / `yarn <name>` is caught separately by
# `_local_only_token_patterns`.
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


def _local_only_token_patterns(
    names: frozenset[str] | set[str] | None = None,
) -> dict[str, re.Pattern[str]]:
    """Word-boundary regex per script name (closes pnpm bare-shortcut form).

    S5U-611 Gap 3 closed bare `pnpm <name>`. S5U-637: `names` widens the
    set to `LOCAL_ONLY_SCRIPTS | tainted` at the caller, catching
    renamed tainted scripts. Defaults to `LOCAL_ONLY_SCRIPTS`.
    """
    effective = LOCAL_ONLY_SCRIPTS if names is None else names
    patterns: dict[str, re.Pattern[str]] = {}
    for name in effective:
        # Bounded: `test-visual-update-lib` must not match `test:visual:update`.
        patterns[name] = re.compile(
            r"""(^|[\s"'`])""" + re.escape(name) + r"""([\s"'`]|$)""",
        )
    return patterns


def _scan_line_for_script_refs(
    line: str,
    rel: str,
    line_no: int,
    tainted: frozenset[str],
    token_patterns: dict[str, re.Pattern[str]],
) -> list[Violation]:
    """Two-layer script-ref scan for one line.

    L1: canonical `(pnpm|npm|yarn) run[-script] <name>` ∩ tainted (S5U-608).
    L2: word-bounded name over `LOCAL_ONLY_SCRIPTS | tainted` (S5U-611/637);
    L2 tainted hits are dedup'd against L1 canonical hits on the same line.
    """
    out: list[Violation] = []
    canonical_hits = _extract_script_names(line) & tainted if tainted else set()
    if canonical_hits:
        names = ", ".join(sorted(canonical_hits))
        out.append(
            Violation(
                path=rel,
                line=line_no,
                excerpt=line,
                reason=f"workflow-invokes-tainted-script ({names})",
            )
        )
    hits = sorted(n for n, pat in token_patterns.items() if pat.search(line))
    if not hits:
        return out
    local_only = [n for n in hits if n in LOCAL_ONLY_SCRIPTS]
    tainted_only = [n for n in hits if n in tainted and n not in LOCAL_ONLY_SCRIPTS]
    if local_only:
        names = ", ".join(local_only)
        out.append(
            Violation(
                path=rel,
                line=line_no,
                excerpt=line,
                reason=f"workflow-invokes-local-only-script ({names})",
            )
        )
    # Dedup tainted layer-2 against layer-1 canonical hits on same line.
    layer2_new = [n for n in tainted_only if n not in canonical_hits]
    if layer2_new:
        names = ", ".join(layer2_new)
        out.append(
            Violation(
                path=rel,
                line=line_no,
                excerpt=line,
                reason=f"workflow-invokes-tainted-script ({names})",
            )
        )
    return out


def _scan_workflow_script_refs(
    workflow_files: list[Path],
    scripts: dict[str, str],
    repo_root: Path,
) -> list[Violation]:
    """Block workflow `run:` lines invoking a forbidden or local-only script.

    S5U-637: token-pattern set is `LOCAL_ONLY_SCRIPTS | tainted`, so a
    renamed tainted script invoked via `pnpm <name>` is caught.
    """
    violations: list[Violation] = []
    tainted = frozenset(name for name, cmd in scripts.items() if _contains_forbidden_flag(cmd))
    token_patterns = _local_only_token_patterns(LOCAL_ONLY_SCRIPTS | tainted)
    if not tainted and not token_patterns:
        return violations
    for path in workflow_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue  # already reported by _scan_github_file
        rel = _rel(path, repo_root)
        for i, line in enumerate(text.splitlines(), start=1):
            violations.extend(_scan_line_for_script_refs(line, rel, i, tainted, token_patterns))
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

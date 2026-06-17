#!/usr/bin/env python3
"""Fail CI when a safety-gate detector changes without updating its corpus.

S5U-789 (acceptance criterion 4). The structural fix for the "patch one regex
variant at a time" treadmill is to make each detector's named adversarial
corpus the contract: a reviewer-found bypass is added as a corpus `block`
case, not patched in as a one-off regex. This guard enforces the coupling — if
a PR touches a detector source file but does NOT touch that detector's corpus
file, CI fails.

A corpus lives at ``apps/pipeline/tests/safety_gate_corpus/<policy>.toml`` and
declares the detector source file(s) it covers::

    policy = "maxdiffpixelratio"
    detector_sources = ["scripts/check_visual_test_overrides.py"]
    [[case]]
    ...

"Documented N/A" exemption (criterion 4): touching the corpus file satisfies
the gate. For a net-zero refactor with no behavioral change, add a
``# coverage-waiver: S5U-XXX <reason>`` comment line to the corpus file — the
corpus-file diff is reviewer-visible and the reviewer judges the waiver (same
shape as the S5U-662 stage-version rule). The guard does not parse the waiver;
the corpus appearing in the diff is the signal.

Per ``.claude/rules/guards.md``:

- **Rule G1** (fail-closed defaults): unresolvable base/head ref (shallow
  checkout), ``git diff`` failure, corpus TOML parse error, missing
  ``detector_sources`` key, and a ``detector_sources`` entry pointing at a
  nonexistent path each exit non-zero with a clear message. A missing corpus
  directory is fail-closed (the guard cannot verify and must not pass blind).
- **No silent caps**: detectors with no corpus yet (parametrize,
  instruction-drift, …) are simply not tracked; the guard prints the covered
  policy set so the rollout boundary is auditable, not hidden.

This guard is the *meta*-gate, not a "detector policy", so it does not require
a corpus of its own.

Usage:
    uv run python scripts/check_detector_corpus_coverage.py \\
        --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from _git_baseline import get_changed_files, verify_ref_exists

DEFAULT_CORPUS_DIR = Path("apps/pipeline/tests/safety_gate_corpus")


@dataclass(frozen=True)
class Policy:
    """A corpus file and the detector source files it is the contract for."""

    name: str
    corpus_rel: str
    detector_sources: tuple[str, ...]


def load_policies(repo_root: Path, corpus_dir: Path) -> list[Policy]:
    """Discover and validate every corpus file. Fail closed on any defect."""
    abs_corpus_dir = corpus_dir if corpus_dir.is_absolute() else repo_root / corpus_dir
    if not abs_corpus_dir.is_dir():
        raise SystemExit(
            f"ERROR: corpus directory {abs_corpus_dir} does not exist.\n"
            "  The coverage guard cannot verify detector/corpus coupling and\n"
            "  fails closed (Rule G1)."
        )

    policies: list[Policy] = []
    for path in sorted(abs_corpus_dir.glob("*.toml")):
        rel = str(path.relative_to(repo_root))
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise SystemExit(f"ERROR: cannot parse corpus {rel}: {exc}") from exc

        name = data.get("policy")
        if not isinstance(name, str) or not name:
            raise SystemExit(f"ERROR: corpus {rel} missing string `policy` key.")

        sources = data.get("detector_sources")
        if not isinstance(sources, list) or not sources:
            raise SystemExit(f"ERROR: corpus {rel} missing non-empty `detector_sources` list.")
        for src in sources:
            if not isinstance(src, str) or not src:
                raise SystemExit(f"ERROR: corpus {rel} has a non-string `detector_sources` entry.")
            if not (repo_root / src).exists():
                raise SystemExit(
                    f"ERROR: corpus {rel} declares detector_source '{src}' which does\n"
                    "  not exist on disk. A corpus pointing at a missing detector\n"
                    "  cannot be verified and fails closed (Rule G1)."
                )

        policies.append(Policy(name=name, corpus_rel=rel, detector_sources=tuple(sources)))
    return policies


def find_violations(policies: list[Policy], changed: set[str]) -> list[str]:
    """Return a message per policy whose detector changed but corpus did not."""
    violations: list[str] = []
    for policy in policies:
        touched = sorted(set(policy.detector_sources) & changed)
        if touched and policy.corpus_rel not in changed:
            violations.append(
                f"policy '{policy.name}': detector source(s) {touched} changed but\n"
                f"  the corpus {policy.corpus_rel} was not. Add the reviewer-found\n"
                "  bypass as a `block` case, or — for a net-zero refactor — add a\n"
                "  `# coverage-waiver: S5U-XXX <reason>` comment to the corpus file."
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head ref (default HEAD)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="Corpus directory (repo-relative or absolute).",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    # Pin git to repo_root so the diff cannot diverge from the root used to
    # compute corpus-relative paths (review NIT: CWD vs --repo-root).
    git_cwd = str(repo_root)
    verify_ref_exists(args.base, cwd=git_cwd)
    verify_ref_exists(args.head, cwd=git_cwd)
    changed = set(get_changed_files(args.base, args.head, cwd=git_cwd))
    policies = load_policies(repo_root, args.corpus_dir)

    covered = ", ".join(p.name for p in policies) or "(none)"
    print(f"detector-corpus-coverage: tracking {len(policies)} policy(ies): {covered}")

    violations = find_violations(policies, changed)
    if violations:
        print(
            "::error::detector-corpus-coverage: a safety-gate detector changed "
            "without a matching corpus update. The corpus is the contract "
            "(S5U-789): reviewer-found bypasses go in as `block` cases, not "
            "one-off regexes.",
            file=sys.stderr,
        )
        for msg in violations:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print("detector-corpus-coverage: clean (no detector changed without its corpus).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

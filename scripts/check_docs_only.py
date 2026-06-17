#!/usr/bin/env python3
"""Classify a PR's change set as docs-only for in-job CI short-circuiting (S5U-1233).

This is a SAFETY-GATE helper. The two rendering-dependent CI jobs
(`web / test`, `visual-regression / visual`) call this script to decide whether
they may short-circuit their expensive steps (Playwright build/e2e, web
build/test) to a GREEN result. A docs-only PR has zero rendering impact, so the
heavy steps add no signal.

A fail-OPEN classifier here would let a code-bearing PR skip a required CI
check entirely, so the classifier is deliberately conservative and fail-closed
on every axis:

- **Conservative allowlist (inverted Rule G2):** "docs-only" means the change
  set is NON-EMPTY *and* EVERY changed file matches a TIGHT allowlist — a `.md`
  extension (case-insensitive) and nothing else. Any other file type — every
  `*.py`/`*.ts`/`*.tsx`/`*.js`/`*.mjs`/`*.toml`/`*.json`/`*.yml`/`*.yaml`/`*.css`,
  lockfiles, `packages/**`, `apps/**` source, `scripts/**`, `.github/**`, and the
  visual baseline PNGs — is NOT in the allowlist (it is "not `.md`"), so its
  presence forces a full run. An empty change set is treated as NOT docs-only.

- **Fail-closed on indeterminate diff (Rule G1):** if the change set cannot be
  determined — unresolvable base ref, shallow checkout, `git diff` failure —
  the shared `scripts/_git_baseline.py` helpers raise ``SystemExit``. ``main()``
  catches that (and any unexpected error) and emits ``docs_only=false`` while
  exiting 0, so the required check still posts a conclusion AND the heavy steps
  run. An indeterminate diff is NEVER short-circuited to green.

``main()`` writes ``docs_only=true`` / ``docs_only=false`` to ``$GITHUB_OUTPUT``
(addressable as ``steps.<id>.outputs.docs_only`` in a later step ``if:``) and
always exits 0 — never crashing the calling job, which would leave the required
check failed/noisy. The default in every error path is ``false`` (run full).

Usage:
    python scripts/check_docs_only.py --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from _git_baseline import get_changed_files, verify_ref_exists

# Inverted-G2 conservative allowlist: the ONLY extension a docs-only PR may
# contain. Lower-cased for case-insensitive matching. Deliberately an EXTENSION
# match, not a directory match: `docs/` happens to be 100% `.md` today, but a
# non-`.md` file dropped anywhere (including `docs/`) must force a full run.
DOCS_ONLY_SUFFIXES: frozenset[str] = frozenset({".md"})


def is_docs_file(path: str) -> bool:
    """Return True only if ``path`` is in the tight docs allowlist (a ``.md`` file).

    Case-insensitive on the suffix so ``X.MD`` counts; ``X.markdown`` does NOT
    (it is not in the allowlist — conservative by design).
    """
    return Path(path).suffix.lower() in DOCS_ONLY_SUFFIXES


def classify_docs_only(changed_files: list[str]) -> bool:
    """Return True iff the change set is non-empty AND every file is a docs file.

    An empty change set returns False: "nothing detectable changed" is NOT a
    licence to skip a required check (it usually means an indeterminate diff
    upstream, which the caller already fails closed on, but this is a second
    belt — a genuinely empty diff is also not classified docs-only).
    """
    if not changed_files:
        return False
    return all(is_docs_file(path) for path in changed_files)


def _write_output(docs_only: bool) -> None:
    """Write ``docs_only=...`` to ``$GITHUB_OUTPUT`` if present; always echo to stdout."""
    value = "true" if docs_only else "false"
    print(f"docs_only={value}")
    gh_out_path = os.environ.get("GITHUB_OUTPUT", "")
    if gh_out_path:
        with open(gh_out_path, "a", encoding="utf-8") as handle:
            handle.write(f"docs_only={value}\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. ALWAYS exits 0; defaults to ``docs_only=false`` on any error.

    Exiting 0 unconditionally keeps the calling required-check job green-able:
    the classifier never fails the job. Fail-closed safety lives in the *value*
    (``false`` => run the full stack), not in the exit code.
    """
    parser = argparse.ArgumentParser(description="Classify a change set as docs-only (S5U-1233).")
    parser.add_argument("--base", required=True, help="Base ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    args = parser.parse_args(argv)

    try:
        # Fail closed (Rule G1): an unresolvable base/head ref (shallow checkout,
        # unfetched remote) raises SystemExit inside these helpers; we catch it
        # below and emit docs_only=false rather than letting an indeterminate
        # diff masquerade as docs-only.
        verify_ref_exists(args.base)
        verify_ref_exists(args.head)
        changed = get_changed_files(args.base, args.head)
    except SystemExit as exc:
        # Indeterminate diff -> NOT docs-only. Surface why, but do not fail the job.
        print(
            f"check_docs_only: indeterminate diff, defaulting to docs_only=false "
            f"(run full stack). Cause: {exc}",
            file=sys.stderr,
        )
        _write_output(False)
        return 0
    except Exception as exc:  # pragma: no cover - defensive; never let the job crash
        print(
            f"check_docs_only: unexpected error, defaulting to docs_only=false "
            f"(run full stack). Cause: {exc!r}",
            file=sys.stderr,
        )
        _write_output(False)
        return 0

    docs_only = classify_docs_only(changed)
    if docs_only:
        print(
            f"check_docs_only: docs-only change set ({len(changed)} file(s), all *.md) "
            "-> rendering jobs may short-circuit to green.",
            file=sys.stderr,
        )
    else:
        non_docs = [p for p in changed if not is_docs_file(p)]
        reason = "empty change set" if not changed else f"{len(non_docs)} non-docs file(s)"
        print(
            f"check_docs_only: NOT docs-only ({reason}) -> run the full stack. "
            f"Sample non-docs: {non_docs[:5]}",
            file=sys.stderr,
        )
    _write_output(docs_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())

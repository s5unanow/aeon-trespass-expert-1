"""Shared git-baseline helpers for safety-gate `check_*.py` scripts (S5U-1232).

Before S5U-1232, `verify_ref_exists` and `get_changed_files` were copy-pasted
across ~6 `scripts/check_*.py` with drifting signatures and — in one copy
(`check_code_erosion.py`) — a latent fail-OPEN that returned `[]` instead of
raising when both git-diff tiers failed. This module is the single source of
truth.

Both helpers fail CLOSED on degenerate inputs per `.claude/rules/guards.md`
Rule G1 (the S5U-642 retrospective): an unresolvable base/head ref (shallow
checkout, unfetched remote branch, typo) or a git subprocess failure must NOT
silently produce an empty diff — it must hard-fail with a clear message so a
misconfigured CI checkout cannot masquerade as "nothing to check."

`cwd` (keyword-only) pins the git invocation to a specific directory so a
caller can keep the diff aligned with a `--repo-root` used elsewhere. Callers
that omit it get the process CWD — byte-identical to the pre-extraction copies
that took no `cwd`.
"""

from __future__ import annotations

import subprocess


def verify_ref_exists(ref: str, *, cwd: str | None = None) -> None:
    """Fail closed if ``ref`` does not resolve to a commit (Rule G1).

    An unresolvable base or head ref (shallow checkout, unfetched remote
    branch, typo) must NOT silently produce an empty diff — it must hard-fail
    with a clear message.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: cannot resolve ref '{ref}' to a commit.\n"
            "  This usually means the CI checkout is shallow and the ref\n"
            "  is unreachable. Set `fetch-depth: 0` on the\n"
            "  actions/checkout step, or pass --base / --head explicitly.\n"
            f"  git rev-parse stderr: {result.stderr.strip()}"
        )


def get_changed_files(base: str, head: str, *, cwd: str | None = None) -> list[str]:
    """Files changed between ``base`` and ``head`` (Rule G1 fail-closed).

    Fails closed when BOTH the merge-base diff (``A...B``) and the direct diff
    (``A B``) fail. The two-tier fallback is preserved because ``A...B``
    requires a reachable merge-base, which does not exist for disjoint
    histories — but "both subprocess calls failed" is NEVER silently treated as
    "no changes."
    """
    primary = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if primary.returncode == 0:
        return [line.strip() for line in primary.stdout.splitlines() if line.strip()]
    fallback = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if fallback.returncode == 0:
        return [line.strip() for line in fallback.stdout.splitlines() if line.strip()]
    raise SystemExit(
        f"ERROR: git diff failed for both '{base}...{head}' and '{base} {head}'.\n"
        f"  primary stderr: {primary.stderr.strip()}\n"
        f"  fallback stderr: {fallback.stderr.strip()}"
    )

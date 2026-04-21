#!/usr/bin/env bash
# S5U-691: regression test for test_pre_pr_safety_gate.sh's main-branch skip
# path. Simulates the post-merge CI environment by invoking the harness with
# CUR_BRANCH=main (via HARNESS_BRANCH_OVERRIDE) in a context where the diff
# against the base ref is empty. Asserts that the harness prints
# `ALL TESTS PASSED` and exits 0 — the behavior that S5U-673 documented but
# did not actually verify.
#
# Before S5U-691, this test would be RED: the harness dies silently at the
# CUR_ISSUE_NUM= grep pipeline under `set -euo pipefail` because `grep -oiE
# 's5u-[0-9]+'` against "main" exits 1, pipefail propagates, set -e kills the
# script before reaching the skip-on-main branch.
#
# Per .claude/rules/guards.md Rule G1: this is the "shallow-checkout /
# missing-state scenario" coverage for the harness's own main-branch fallback.
#
# Run: bash scripts/test_harness_skip_on_main.sh
# Expected: "REGRESSION TEST PASSED" and exit 0.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HARNESS_SCRIPT="$REPO_ROOT/scripts/test_pre_pr_safety_gate.sh"

if [ ! -f "$HARNESS_SCRIPT" ]; then
  echo "FAIL [regression]: harness script not found at $HARNESS_SCRIPT"
  exit 1
fi

# The strategy: we can't easily switch the real repo to main mid-run (CI
# and local dev may be on a feature branch). Instead, we use
# HARNESS_BRANCH_OVERRIDE=main to force the harness to treat CUR_BRANCH as
# "main" for its issue-number / skip-on-main decision logic.
#
# BUT: the harness also computes `git diff --name-only main...HEAD` from the
# real repo. On a feature branch with safety-gate-scoped changes, that diff
# is non-empty, and the skip-on-main branch wouldn't fire (the harness would
# proceed to Layer 3 tests).
#
# To reach the skip-on-main path, we need both:
#   (a) CUR_BRANCH="main" (via HARNESS_BRANCH_OVERRIDE)
#   (b) The real repo's `main...HEAD` diff to be empty of safety-gate paths
#
# (b) holds on `main` itself (push events) and on any feature branch whose
# safety-gate paths are unchanged. On this PR's branch, (b) does NOT hold
# (we're editing safety-gate files), so we can't test via the real repo.
#
# Solution: construct an ephemeral git worktree where HEAD == base == a
# commit with no safety-gate changes vs itself. Invoke the harness from
# within that worktree via a copy of the repo.
#
# Simpler solution: create a throwaway commit on `main` in a detached
# worktree and run the harness there. But we need the harness to resolve
# REPO_ROOT to that worktree, which happens because REPO_ROOT is computed
# from `dirname "${BASH_SOURCE[0]}"`.

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Approach: git clone --no-local the current repo to TMPDIR. The clone
# receives ALL branches; we then force the ephemeral repo's `main` ref to
# point at the CURRENT HEAD of the calling invocation (i.e. the fix's
# working tree-equivalent HEAD), and check out that state as `main`.
#
# Why not just `git checkout main` in the clone? Because the clone's `main`
# would reflect the real repo's origin/main — which, on the fix-branch run
# invoked locally, is the PRE-fix version (the bug we're regressing against).
# The regression test must verify that the FIX makes the skip path work, so
# it must run the fixed harness, not the pre-fix one.
#
# Resolution: determine the caller's current HEAD SHA, then in the clone
# create (or reset) `main` to that SHA before checkout. On the fix-branch
# CI run, this means `main` in the clone points at the fix commit. On a
# real post-merge main CI run (where HEAD is literally main and already
# contains the fix), it's idempotent.
echo "Setting up ephemeral repo at $TMPDIR/repo ..."
CALLER_HEAD_SHA=$(cd "$REPO_ROOT" && git rev-parse HEAD)
echo "Caller HEAD SHA: $CALLER_HEAD_SHA"

# Use --no-local to avoid hardlinks; origin of the clone is the real repo.
git clone --quiet --no-local "$REPO_ROOT" "$TMPDIR/repo"

cd "$TMPDIR/repo"

# Force ephemeral `main` to point at the caller's HEAD SHA so the harness
# under test is the CURRENT harness (with the S5U-691 fix), not whatever
# main happened to contain when the clone was taken.
if ! git rev-parse --verify "$CALLER_HEAD_SHA^{commit}" >/dev/null 2>&1; then
  echo "FAIL [regression]: caller HEAD SHA $CALLER_HEAD_SHA not resolvable in ephemeral clone."
  exit 1
fi
git checkout --quiet -B main "$CALLER_HEAD_SHA"

# Sanity: the diff main...HEAD in the ephemeral clone should be empty of
# safety-gate paths (HEAD == main here).
DIFF_LINES=$(git diff --name-only main...HEAD | wc -l | tr -d '[:space:]')
if [ "$DIFF_LINES" != "0" ]; then
  echo "FAIL [regression]: ephemeral clone on main has non-zero diff against self — harness will not take skip path."
  exit 1
fi

# Run the harness from the ephemeral repo. Its REPO_ROOT resolves to
# $TMPDIR/repo by virtue of BASH_SOURCE. Without HARNESS_BRANCH_OVERRIDE the
# harness falls back to `git rev-parse --abbrev-ref HEAD`, which is "main".
HARNESS_LOG=$(mktemp)
set +e
bash "$TMPDIR/repo/scripts/test_pre_pr_safety_gate.sh" >"$HARNESS_LOG" 2>&1
HARNESS_RC=$?
set -e

echo ""
echo "Harness exit code: $HARNESS_RC"
echo "Harness stdout (last 20 lines):"
tail -20 "$HARNESS_LOG" | sed 's/^/  /'
echo ""

# Assertions
FAILED=0

if [ "$HARNESS_RC" != "0" ]; then
  echo "FAIL [regression]: harness exited $HARNESS_RC (expected 0)"
  FAILED=1
fi

if ! grep -q "ALL TESTS PASSED" "$HARNESS_LOG"; then
  echo "FAIL [regression]: harness output lacks 'ALL TESTS PASSED'"
  FAILED=1
fi

if ! grep -q "SKIP \[layer 3 harness\]: on 'main' with no pending safety-gate diff" "$HARNESS_LOG"; then
  echo "FAIL [regression]: harness output lacks the expected SKIP banner"
  FAILED=1
fi

rm -f "$HARNESS_LOG"

if [ "$FAILED" -ne 0 ]; then
  echo ""
  echo "REGRESSION TEST FAILED — S5U-691's main-branch skip path is broken."
  exit 1
fi

echo "REGRESSION TEST PASSED"

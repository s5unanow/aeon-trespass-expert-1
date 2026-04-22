#!/usr/bin/env bash
# S5U-696: regression test for test_pre_pr_safety_gate.sh's feature-branch
# SKIP path. Simulates a feature PR (pure pipeline / web / schemas / docs)
# where `main...HEAD` has a non-empty diff but NO paths match the safety-gate
# regex. Asserts that the harness prints `ALL TESTS PASSED` and exits 0 —
# the behavior S5U-696 broadens the SKIP branch to cover.
#
# Before S5U-696, this test is RED: the harness takes the FAIL branch at
# lines 322-326 with "current branch '<name>' has no safety-gate paths in
# main...HEAD" and exits 1. This failed `python / test` for every non-safety-
# gate PR (see S5U-588's CI run 24736661224 job 72365216373 for the
# in-the-wild instance).
#
# Per .claude/rules/guards.md Rule G1: complements test_harness_skip_on_main.sh
# by covering the second branch of the (now broadened) empty-safety-gate-diff
# SKIP path. Together the two tests pin both names: main-branch and
# feature-branch SKIPs both exit 0 with banners.
#
# Run: bash scripts/test_harness_skip_on_feature_branch.sh
# Expected: "REGRESSION TEST PASSED" and exit 0.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HARNESS_SCRIPT="$REPO_ROOT/scripts/test_pre_pr_safety_gate.sh"

if [ ! -f "$HARNESS_SCRIPT" ]; then
  echo "FAIL [regression]: harness script not found at $HARNESS_SCRIPT"
  exit 1
fi

# Strategy — analogous to test_harness_skip_on_main.sh but with a feature
# branch layout:
#
#   1. Clone the real repo to an ephemeral TMPDIR via `git clone --no-local`.
#   2. In the clone, force `main` to point at the caller's HEAD SHA so the
#      harness-under-test is the CURRENT harness (with the S5U-696 fix), not
#      whatever origin/main happened to contain when the clone was taken.
#   3. Create a feature branch `s5unanow/s5u-696-regression-synthetic` on top
#      of main that adds ONE commit touching only `README.md` (a path that
#      does NOT match the hook's safety-gate regex).
#   4. Invoke the harness from the feature branch. The harness computes
#      SAFETY_DIFF_CHECK from `git diff --name-only main...HEAD`, which picks
#      up the README change but sees no safety-gate paths, so the SKIP branch
#      must fire under S5U-696 even though CUR_BRANCH != 'main'.
#   5. Assert harness exits 0, prints "ALL TESTS PASSED", and prints the new
#      SKIP banner ("branch '<name>' has no safety-gate diff in main...HEAD").

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Setting up ephemeral repo at $TMPDIR/repo ..."
CALLER_HEAD_SHA=$(cd "$REPO_ROOT" && git rev-parse HEAD)
echo "Caller HEAD SHA: $CALLER_HEAD_SHA"

# --no-local avoids hardlinks so mutations of the ephemeral repo can't leak
# back into the calling repo's objects database.
git clone --quiet --no-local "$REPO_ROOT" "$TMPDIR/repo"

cd "$TMPDIR/repo"

# Configure a deterministic committer so the synthetic commit is reproducible.
git config user.email "harness@example.com"
git config user.name "S5U-696 Harness"

# Force ephemeral `main` to point at the caller's HEAD SHA so the harness
# under test is the CURRENT harness, not whatever main was at clone-time.
if ! git rev-parse --verify "$CALLER_HEAD_SHA^{commit}" >/dev/null 2>&1; then
  echo "FAIL [regression]: caller HEAD SHA $CALLER_HEAD_SHA not resolvable in ephemeral clone."
  exit 1
fi
git checkout --quiet -B main "$CALLER_HEAD_SHA"

# Create the synthetic feature branch. Name matches the s5unanow/s5u-<N>-...
# pattern so the harness's CUR_ISSUE_NUM guard doesn't short-circuit on a
# non-namespaced branch (we want to reach the SAFETY_DIFF_CHECK gate, which
# post-S5U-696 runs BEFORE the issue-num guard — but we keep the name
# conformant so the test doesn't rely on the gate ordering quirk).
SYNTHETIC_BRANCH="s5unanow/s5u-696-regression-synthetic"
git checkout --quiet -B "$SYNTHETIC_BRANCH" main

# Apply a non-safety-gate change. README.md at the repo root is not matched by
# any branch of the hook's safety-gate regex (.claude/hooks/, .claude/skills/,
# .github/workflows/, .github/actions/, scripts/check_*, scripts/pre-*,
# CLAUDE.md, .claude/prompts/review.md, .claude/coordinator-signers.txt,
# scripts/test_pre_pr_safety_gate.sh). Appending a harmless line is enough to
# make main...HEAD non-empty while leaving SAFETY_DIFF_CHECK empty.
if [ ! -f README.md ]; then
  echo "# synthetic README" > README.md
else
  printf '\n<!-- S5U-696 harness synthetic marker -->\n' >> README.md
fi
git add README.md
git commit --quiet -m "S5U-696: synthetic non-safety-gate change for harness regression test"

# Sanity: main...HEAD must be non-empty (proves the commit landed) AND the
# harness's safety-gate regex must match zero files in that diff (proves the
# path is genuinely non-safety-gate).
DIFF_ALL=$(git diff --name-only main...HEAD)
if [ -z "$DIFF_ALL" ]; then
  echo "FAIL [regression]: ephemeral feature branch has empty diff against main — test precondition violated."
  exit 1
fi
# Extract the same regex the harness extracts. Keep this in lockstep with the
# harness's own extraction at test_pre_pr_safety_gate.sh:44-45.
SAFETY_REGEX=$(grep -oE "\\| grep -E '\\^\\([^']+\\)'" "$TMPDIR/repo/.claude/hooks/pre-pr-check.sh" | head -1 \
  | sed -E "s/^\| grep -E '//; s/'$//")
if [ -z "$SAFETY_REGEX" ]; then
  echo "FAIL [regression]: could not extract safety-gate regex — harness precondition violated."
  exit 1
fi
SAFETY_MATCHES=$(echo "$DIFF_ALL" | grep -E "$SAFETY_REGEX" || true)
if [ -n "$SAFETY_MATCHES" ]; then
  echo "FAIL [regression]: synthetic diff unexpectedly matches safety-gate regex:"
  echo "$SAFETY_MATCHES" | sed 's/^/    /'
  exit 1
fi

echo "Synthetic diff against main (must be non-safety-gate):"
echo "$DIFF_ALL" | sed 's/^/  /'
echo ""

# Run the harness from the ephemeral repo. REPO_ROOT inside the harness
# resolves to $TMPDIR/repo via BASH_SOURCE. Without HARNESS_BRANCH_OVERRIDE
# the harness falls back to `git rev-parse --abbrev-ref HEAD`, which is the
# synthetic feature branch name.
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

FAILED=0

if [ "$HARNESS_RC" != "0" ]; then
  echo "FAIL [regression]: harness exited $HARNESS_RC (expected 0)"
  FAILED=1
fi

if ! grep -q "ALL TESTS PASSED" "$HARNESS_LOG"; then
  echo "FAIL [regression]: harness output lacks 'ALL TESTS PASSED'"
  FAILED=1
fi

# The new banner from S5U-696. Precise substring to confirm the broadened
# SKIP path fired (not the old main-only one and not a different SKIP).
if ! grep -q "SKIP \[layer 3 harness\]: branch '$SYNTHETIC_BRANCH' has no safety-gate diff in main\.\.\.HEAD\." "$HARNESS_LOG"; then
  echo "FAIL [regression]: harness output lacks the expected feature-branch SKIP banner"
  echo "  Expected substring: SKIP [layer 3 harness]: branch '$SYNTHETIC_BRANCH' has no safety-gate diff in main...HEAD."
  FAILED=1
fi

rm -f "$HARNESS_LOG"

if [ "$FAILED" -ne 0 ]; then
  echo ""
  echo "REGRESSION TEST FAILED — S5U-696's feature-branch skip path is broken."
  exit 1
fi

echo "REGRESSION TEST PASSED"

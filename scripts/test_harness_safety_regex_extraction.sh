#!/usr/bin/env bash
# S5U-692: regression test for test_pre_pr_safety_gate.sh's SAFETY_REGEX
# extraction at lines 44-45. Simulates a future refactor of the hook's
# safety-gate anchor (e.g., `| grep -E '^(...)'` → `| grep --extended-regexp
# '^(...)'`) and asserts the harness reaches its explicit fail-closed branch
# at line 47 instead of silently crashing under `set -euo pipefail`.
#
# Before S5U-692 this test is RED: the harness dies silently at the line-44
# grep pipeline because `grep -oE` exits 1 on no match, `pipefail` propagates,
# and `set -e` kills the script before the `if [ -z "$SAFETY_REGEX" ]` guard
# at line 47 can fire.
#
# After S5U-692 (`|| true` appended to the line-44 pipeline), the empty-match
# path reaches line 47 and emits the diagnostic `FAIL: could not extract
# safety-gate regex from <hook>`.
#
# Per .claude/rules/guards.md Rule G1: this is the "parse-error / missing-state"
# coverage for the harness's own hook-extraction step. The companion sibling
# scripts/test_harness_skip_on_main.sh covers the CUR_ISSUE_NUM extraction
# fixed by S5U-691 in the same file.
#
# Run: bash scripts/test_harness_safety_regex_extraction.sh
# Expected: "REGRESSION TEST PASSED" and exit 0.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HARNESS_SCRIPT="$REPO_ROOT/scripts/test_pre_pr_safety_gate.sh"
HOOK_SCRIPT="$REPO_ROOT/.claude/hooks/pre-pr-check.sh"

if [ ! -f "$HARNESS_SCRIPT" ]; then
  echo "FAIL [regression]: harness script not found at $HARNESS_SCRIPT"
  exit 1
fi
if [ ! -f "$HOOK_SCRIPT" ]; then
  echo "FAIL [regression]: hook script not found at $HOOK_SCRIPT"
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Copy both scripts into the tempdir. We rewrite the harness's HOOK_SCRIPT
# path to point at our refactored copy. This keeps the real repo untouched
# and avoids needing a git clone — the line-44 extraction runs before the
# harness reaches any git-dependent logic.
cp "$HARNESS_SCRIPT" "$TMPDIR/harness.sh"
cp "$HOOK_SCRIPT" "$TMPDIR/hook_refactored.sh"

# Refactor the hook's safety-gate anchor from `| grep -E '^(...)` to
# `| grep --extended-regexp '^(...)`. This is the exact rename scenario the
# issue's repro recipe describes.
sed -i.bak "s/| grep -E '\\^(/| grep --extended-regexp '^(/" "$TMPDIR/hook_refactored.sh"
rm -f "$TMPDIR/hook_refactored.sh.bak"

# Sanity-check the refactor actually landed: the old form must be gone and
# the new form must be present. A sed that silently matches nothing would
# produce a false PASS here.
if grep -q "| grep -E '\\^(" "$TMPDIR/hook_refactored.sh"; then
  echo "FAIL [regression setup]: old anchor form '| grep -E '^(' is still present in refactored hook"
  exit 1
fi
if ! grep -q "| grep --extended-regexp '^(" "$TMPDIR/hook_refactored.sh"; then
  echo "FAIL [regression setup]: new anchor form '| grep --extended-regexp '^(' not in refactored hook"
  exit 1
fi

# Point the harness copy at the refactored hook. The harness's HOOK_SCRIPT
# assignment sits right below REPO_ROOT; rewrite the literal path assignment.
sed -i.bak "s|^HOOK_SCRIPT=\"\$REPO_ROOT/.claude/hooks/pre-pr-check.sh\"\$|HOOK_SCRIPT=\"$TMPDIR/hook_refactored.sh\"|" "$TMPDIR/harness.sh"
rm -f "$TMPDIR/harness.sh.bak"

# Sanity-check the rewrite landed.
if ! grep -q "^HOOK_SCRIPT=\"$TMPDIR/hook_refactored.sh\"\$" "$TMPDIR/harness.sh"; then
  echo "FAIL [regression setup]: HOOK_SCRIPT assignment not rewritten in harness copy"
  grep -n '^HOOK_SCRIPT=' "$TMPDIR/harness.sh" | sed 's/^/       /'
  exit 1
fi

# Run the rewritten harness. It should hit the line-44 extraction, find no
# match (because the anchor was refactored), fall through to the line-47
# guard via `|| true`, and exit 1 with the diagnostic message.
HARNESS_LOG=$(mktemp)
set +e
bash "$TMPDIR/harness.sh" >"$HARNESS_LOG" 2>&1
HARNESS_RC=$?
set -e

echo "Harness exit code: $HARNESS_RC"
echo "Harness stdout:"
sed 's/^/  /' "$HARNESS_LOG"
echo ""

FAILED=0

# Assertion 1: exit code must be 1 (the explicit `exit 1` after the
# diagnostic — not silently 1 from set -e).
if [ "$HARNESS_RC" != "1" ]; then
  echo "FAIL [regression]: harness exited $HARNESS_RC (expected 1)"
  FAILED=1
fi

# Assertion 2: the explicit diagnostic must be in the output. This is the
# difference between the pre-fix silent crash (empty output) and the post-fix
# fail-closed branch (diagnostic + exit 1).
if ! grep -qF "FAIL: could not extract safety-gate regex from" "$HARNESS_LOG"; then
  echo "FAIL [regression]: harness output lacks the expected diagnostic"
  echo "  expected substring: 'FAIL: could not extract safety-gate regex from'"
  echo "  pre-S5U-692 the harness silent-crashed before emitting this line."
  FAILED=1
fi

# Assertion 3: the diagnostic must reference our refactored hook path, not
# the real repo's hook — confirming the rewrite and the harness's $HOOK_SCRIPT
# interpolation both worked.
if ! grep -qF "FAIL: could not extract safety-gate regex from $TMPDIR/hook_refactored.sh" "$HARNESS_LOG"; then
  echo "FAIL [regression]: diagnostic does not reference the refactored hook path"
  echo "  expected: 'FAIL: could not extract safety-gate regex from $TMPDIR/hook_refactored.sh'"
  FAILED=1
fi

rm -f "$HARNESS_LOG"

if [ "$FAILED" -ne 0 ]; then
  echo ""
  echo "REGRESSION TEST FAILED — S5U-692's line-44 fail-closed branch is unreachable."
  exit 1
fi

echo "REGRESSION TEST PASSED"

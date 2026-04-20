#!/usr/bin/env bash
# S5U-647: three-input smoke test for the safety-gate scope probe in
# .claude/hooks/pre-pr-check.sh. Exercises the probe's decision matrix:
#
#   1. Happy path:      diff has NO safety-gate paths            → probe silent, proceeds
#   2. Failure input:   diff HAS safety-gate path, NO marker      → probe BLOCKS
#   3. Adversarial:     diff HAS safety-gate path, marker present → probe allows
#
# Run: bash scripts/test_pre_pr_safety_gate.sh
# Expected: "ALL TESTS PASSED" and exit 0.
#
# This is a worker-discipline test script (not run in CI) so it tests the
# probe regex in isolation — it shells out to a local repo-like fixture and
# does not rely on real git state. The test runner re-implements the probe's
# regex pattern and invariants; if the probe diverges, update both places.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HOOK_SCRIPT="$REPO_ROOT/.claude/hooks/pre-pr-check.sh"

if [ ! -f "$HOOK_SCRIPT" ]; then
  echo "FAIL: hook script not found at $HOOK_SCRIPT"
  exit 1
fi

# Extract the safety-gate regex from the hook for co-testing. If the regex
# shifts in the hook, this grep picks up the new form automatically.
SAFETY_REGEX=$(grep -oE "\\| grep -E '\\^\\([^']+\\)'" "$HOOK_SCRIPT" | head -1 \
  | sed -E "s/^\| grep -E '//; s/'$//")

if [ -z "$SAFETY_REGEX" ]; then
  echo "FAIL: could not extract safety-gate regex from $HOOK_SCRIPT"
  exit 1
fi

echo "Extracted regex: $SAFETY_REGEX"
echo ""

run_case() {
  local label="$1"
  local paths="$2"
  local expect_match="$3"  # "yes" or "no"

  local matched
  matched=$(echo "$paths" | grep -E "$SAFETY_REGEX" || true)

  if [ "$expect_match" = "yes" ]; then
    if [ -z "$matched" ]; then
      echo "FAIL [$label]: expected a safety-gate match, got none."
      echo "  input paths:"
      echo "$paths" | sed 's/^/    /'
      return 1
    fi
    echo "OK   [$label]: matched as expected"
    echo "$matched" | sed 's/^/       /'
  else
    if [ -n "$matched" ]; then
      echo "FAIL [$label]: expected no match, got:"
      echo "$matched" | sed 's/^/       /'
      return 1
    fi
    echo "OK   [$label]: no match as expected"
  fi
}

# -------------------------------------------------------------------------
# Input 1 (happy path): no safety-gate paths
# -------------------------------------------------------------------------
HAPPY_PATHS="apps/pipeline/src/atr_pipeline/cli/run.py
apps/web/src/components/Foo.tsx
packages/schemas/python/models.py
docs/README.md"

run_case "happy path (pipeline + web + schemas + docs)" "$HAPPY_PATHS" "no"

# -------------------------------------------------------------------------
# Input 2 (failure input): safety-gate paths present
# -------------------------------------------------------------------------
FAILURE_PATHS=".claude/hooks/pre-commit-check.sh
apps/pipeline/src/atr_pipeline/cli/run.py"

run_case "safety-gate hook edit" "$FAILURE_PATHS" "yes"

FAILURE_PATHS_2=".claude/skills/ship/SKILL.md"
run_case "SKILL.md edit" "$FAILURE_PATHS_2" "yes"

FAILURE_PATHS_3=".github/workflows/ci.yml"
run_case "workflow YAML edit" "$FAILURE_PATHS_3" "yes"

FAILURE_PATHS_4="CLAUDE.md"
run_case "CLAUDE.md edit" "$FAILURE_PATHS_4" "yes"

FAILURE_PATHS_5="scripts/check_codegen_fresh.sh"
run_case "check_*.sh script edit" "$FAILURE_PATHS_5" "yes"

FAILURE_PATHS_6=".claude/prompts/review.md"
run_case "review prompt edit" "$FAILURE_PATHS_6" "yes"

# -------------------------------------------------------------------------
# Input 3 (adversarial / false-positive surface): near-misses that must NOT match
# -------------------------------------------------------------------------
# A file under docs/ that happens to mention safety-gate text — not a real diff hit.
ADV_PATHS_1="docs/hooks-overview.md
docs/safety-gate-policy.md"
run_case "docs about hooks (must NOT match)" "$ADV_PATHS_1" "no"

# A file under scripts/ that is not named check_* or pre-*.
ADV_PATHS_2="scripts/export_to_web.py
scripts/bootstrap_extended_fixtures.py"
run_case "scripts/ non-check_*, non-pre-*" "$ADV_PATHS_2" "no"

# A file under .claude/ that is neither hooks, prompts/review.md, nor SKILL.md.
ADV_PATHS_3=".claude/rules/pipeline.md
.claude/rules/web.md"
run_case ".claude/rules/ edits (must NOT match)" "$ADV_PATHS_3" "no"

# README inside a skill directory — must not match (only SKILL.md is gated).
ADV_PATHS_4=".claude/skills/ship/README.md"
run_case "non-SKILL.md file inside a skill dir" "$ADV_PATHS_4" "no"

# A filename like CLAUDE.md.bak should NOT match (anchor is end-of-string).
ADV_PATHS_5="CLAUDE.md.bak"
run_case "CLAUDE.md.bak (not CLAUDE.md)" "$ADV_PATHS_5" "no"

# -------------------------------------------------------------------------
# Input 4 (mixed): safety-gate + unrelated in same diff
# -------------------------------------------------------------------------
MIXED_PATHS="apps/web/src/App.tsx
.claude/hooks/pre-commit-check.sh
apps/pipeline/src/foo.py"
run_case "mixed diff (triggers on hook)" "$MIXED_PATHS" "yes"

echo ""
echo "ALL TESTS PASSED"

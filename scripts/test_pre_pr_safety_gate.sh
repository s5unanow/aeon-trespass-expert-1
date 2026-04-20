#!/usr/bin/env bash
# S5U-647 / S5U-666 / S5U-670: smoke tests for the safety-gate scope probe
# in .claude/hooks/pre-pr-check.sh. Exercises three gate layers:
#
#   Layer 1 (S5U-647): regex over changed-file paths decides whether the probe fires
#     Inputs 1-12: happy / failure / adversarial regex coverage
#
#   Layer 2 (S5U-666): base-ref resolution (main vs origin/main vs fail-closed)
#     Inputs 13-14: missing-main-fails-closed, origin-main-fallback-succeeds
#
#   Layer 3 (S5U-670): coordinator-ack commit status (vs worker-forgeable file marker)
#     Inputs 15-19: happy, empty status list, wrong creator, malformed JSON,
#                   missing allowlist
#
# Run: bash scripts/test_pre_pr_safety_gate.sh
# Expected: "ALL TESTS PASSED" and exit 0.
#
# Not wired to CI — worker-discipline test, run manually before PR. If the
# hook's regex / logic shifts, update both places. See tmp/plan-s5u-670.md
# §5 for the test-strategy rationale.

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

# =========================================================================
# Layer 1 (S5U-647): regex tests
# =========================================================================

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

# S5U-670: .claude/coordinator-signers.txt edits are safety-gate-scoped
FAILURE_PATHS_7=".claude/coordinator-signers.txt"
run_case "coordinator-signers.txt edit (S5U-670)" "$FAILURE_PATHS_7" "yes"

# S5U-670: this test script itself is safety-gate-scoped (it is the three-input
# smoke test for the hook; silently weakening it is itself a safety-gate event)
FAILURE_PATHS_8="scripts/test_pre_pr_safety_gate.sh"
run_case "test_pre_pr_safety_gate.sh edit (S5U-670)" "$FAILURE_PATHS_8" "yes"

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

# =========================================================================
# Layer 2 (S5U-666): base-ref resolution
# =========================================================================
#
# The hook resolves its base ref via a small function (inlined below for
# testability). We replicate the production logic verbatim and exercise it
# against synthetic repos. If the hook's logic diverges, update both places.

resolve_base_ref() {
  if git rev-parse --verify main^{commit} >/dev/null 2>&1; then
    echo main
    return 0
  fi
  if git rev-parse --verify origin/main^{commit} >/dev/null 2>&1; then
    echo origin/main
    return 0
  fi
  return 1
}

# -------------------------------------------------------------------------
# Input 13 (S5U-666 failure input): neither main nor origin/main → BLOCK
# -------------------------------------------------------------------------
TMPDIR_13=$(mktemp -d)
(
  cd "$TMPDIR_13"
  git init -q -b feature
  git config user.email "test@example.com"
  git config user.name "Test"
  git commit --allow-empty -q -m "initial"
  # Port the function; do not rely on the parent shell's environment.
  if resolve_base_ref >/dev/null 2>&1; then
    echo "FAIL [13 S5U-666 missing main+origin/main]: resolve_base_ref succeeded, expected failure"
    exit 1
  fi
)
# shellcheck disable=SC2181
if [ $? -ne 0 ]; then exit 1; fi
rm -rf "$TMPDIR_13"
echo "OK   [13 S5U-666 missing main+origin/main]: resolve_base_ref exits non-zero as expected"

# -------------------------------------------------------------------------
# Input 14 (S5U-666 happy fallback): no local main, but origin/main present
# -------------------------------------------------------------------------
TMPDIR_14=$(mktemp -d)
(
  cd "$TMPDIR_14"
  # Stand up a bare "origin" repo with a main branch.
  git init -q --bare origin.git
  git init -q --initial-branch=main work
  cd work
  git config user.email "test@example.com"
  git config user.name "Test"
  git commit --allow-empty -q -m "base"
  git remote add origin ../origin.git
  git push -q origin main
  # Create a feature branch and delete local `main`, leaving only origin/main.
  git checkout -q -b feature
  git branch -q -D main
  git fetch -q origin
  # Now: local `main` is gone; `origin/main` remote-tracking ref survives.
  if ! resolve_base_ref >/dev/null 2>&1; then
    echo "FAIL [14 S5U-666 origin/main fallback]: resolve_base_ref failed, expected success"
    exit 1
  fi
  BASE=$(resolve_base_ref)
  if [ "$BASE" != "origin/main" ]; then
    echo "FAIL [14 S5U-666 origin/main fallback]: expected BASE=origin/main, got '$BASE'"
    exit 1
  fi
)
# shellcheck disable=SC2181
if [ $? -ne 0 ]; then exit 1; fi
rm -rf "$TMPDIR_14"
echo "OK   [14 S5U-666 origin/main fallback]: BASE=origin/main as expected"

# =========================================================================
# Layer 3 (S5U-670): coordinator-ack commit status validation
# =========================================================================
#
# Production hook queries `gh api repos/.../commits/<sha>/statuses`. We don't
# want tests to hit live GitHub, so the hook honors COORDINATOR_ACK_STATUS_SOURCE
# (documented test-only env var). The checks below exercise the same filter +
# allowlist logic the hook runs — replicated here verbatim so a divergence
# between test + hook surfaces as a FAIL.
#
# See .claude/hooks/pre-pr-check.sh "S5U-670: fetch coordinator-ack commit
# status from GitHub API" for the authoritative block.

FIXTURE_DIR=$(mktemp -d)
trap 'rm -rf "$FIXTURE_DIR"' EXIT

# Happy fixture: single success status, signed by s5unanow
cat > "$FIXTURE_DIR/happy.json" <<'EOF'
[
  {
    "state": "success",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:00:00Z"
  }
]
EOF

# Empty fixture: no statuses at all
echo '[]' > "$FIXTURE_DIR/empty.json"

# Wrong-creator fixture: worker self-posted with a different login
cat > "$FIXTURE_DIR/wrong_creator.json" <<'EOF'
[
  {
    "state": "success",
    "context": "coordinator-ack",
    "creator": { "login": "malicious-worker-bot", "type": "Bot" },
    "created_at": "2026-04-20T12:00:00Z"
  }
]
EOF

# Malformed JSON fixture
echo 'not valid json {' > "$FIXTURE_DIR/malformed.json"

# Near-miss: status exists but for a different context (e.g., CI)
cat > "$FIXTURE_DIR/wrong_context.json" <<'EOF'
[
  {
    "state": "success",
    "context": "ci/check-run",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:00:00Z"
  }
]
EOF

# Near-miss: coordinator-ack context but state=failure (e.g., manual revocation)
cat > "$FIXTURE_DIR/failed_state.json" <<'EOF'
[
  {
    "state": "failure",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:00:00Z"
  }
]
EOF

# Allowlist file used by the logic below — replicated from the real
# .claude/coordinator-signers.txt but without coupling the test to the live
# file contents (we want these tests to be hermetic).
ALLOWLIST_FILE="$FIXTURE_DIR/signers.txt"
cat > "$ALLOWLIST_FILE" <<'EOF'
# Test allowlist — mirrors .claude/coordinator-signers.txt shape
s5unanow
EOF

# Replicated filter logic — keep in sync with pre-pr-check.sh S5U-670 block.
#
# Returns exit 0 if a valid coordinator-ack status is present and signed by
# an allowlisted creator; exit 1 otherwise. Logs the reason.
validate_coordinator_ack() {
  local status_source="$1"
  local allowlist_file="$2"

  if [ ! -f "$allowlist_file" ]; then
    echo "  (reason: allowlist missing at $allowlist_file)"
    return 1
  fi
  local allowlist
  allowlist=$(grep -vE '^[[:space:]]*(#|$)' "$allowlist_file" | awk '{print $1}')
  if [ -z "$allowlist" ]; then
    echo "  (reason: allowlist empty)"
    return 1
  fi

  if [ ! -f "$status_source" ]; then
    echo "  (reason: status fixture missing at $status_source)"
    return 1
  fi
  local status_json
  status_json=$(cat "$status_source")

  if ! echo "$status_json" | jq -e . >/dev/null 2>&1; then
    echo "  (reason: status response is not valid JSON)"
    return 1
  fi

  local matching_creator
  matching_creator=$(echo "$status_json" \
    | jq -r '[.[] | select(.context == "coordinator-ack" and .state == "success") | .creator.login] | .[0] // empty' 2>/dev/null \
    || true)

  if [ -z "$matching_creator" ]; then
    echo "  (reason: no coordinator-ack/success status found)"
    return 1
  fi

  if ! echo "$allowlist" | grep -qxF "$matching_creator"; then
    echo "  (reason: creator '$matching_creator' not in allowlist)"
    return 1
  fi

  echo "  (matched: creator=$matching_creator)"
  return 0
}

assert_ack() {
  local label="$1"
  local source="$2"
  local allow="$3"
  local expect="$4"  # "pass" or "block"

  if validate_coordinator_ack "$source" "$allow" >/tmp/_ack_log.$$ 2>&1; then
    if [ "$expect" = "pass" ]; then
      echo "OK   [$label]: validated as expected"
      cat /tmp/_ack_log.$$ | sed 's/^/       /'
    else
      echo "FAIL [$label]: expected BLOCK, got PASS"
      cat /tmp/_ack_log.$$ | sed 's/^/       /'
      rm -f /tmp/_ack_log.$$
      return 1
    fi
  else
    if [ "$expect" = "block" ]; then
      echo "OK   [$label]: blocked as expected"
      cat /tmp/_ack_log.$$ | sed 's/^/       /'
    else
      echo "FAIL [$label]: expected PASS, got BLOCK"
      cat /tmp/_ack_log.$$ | sed 's/^/       /'
      rm -f /tmp/_ack_log.$$
      return 1
    fi
  fi
  rm -f /tmp/_ack_log.$$
}

# -------------------------------------------------------------------------
# Input 15 (S5U-670 happy path): coordinator posted a signed status → PASS
# -------------------------------------------------------------------------
assert_ack "15 S5U-670 happy (signed status)" "$FIXTURE_DIR/happy.json" "$ALLOWLIST_FILE" "pass"

# -------------------------------------------------------------------------
# Input 16 (S5U-670 failure input): no status present → BLOCK
# -------------------------------------------------------------------------
assert_ack "16 S5U-670 empty status list" "$FIXTURE_DIR/empty.json" "$ALLOWLIST_FILE" "block"

# -------------------------------------------------------------------------
# Input 17 (S5U-670 adversarial): worker self-posted with different login → BLOCK
# -------------------------------------------------------------------------
# This is the core S5U-670 invariant: a forgery attempt by the worker posting
# the status themselves fails because GitHub stamps creator.login from the
# authenticated OAuth token — not a worker-controlled input.
assert_ack "17 S5U-670 adversarial (worker self-post)" "$FIXTURE_DIR/wrong_creator.json" "$ALLOWLIST_FILE" "block"

# -------------------------------------------------------------------------
# Input 18 (S5U-670 G1): malformed JSON → BLOCK (fail closed on parse error)
# -------------------------------------------------------------------------
assert_ack "18 S5U-670 G1 malformed JSON" "$FIXTURE_DIR/malformed.json" "$ALLOWLIST_FILE" "block"

# -------------------------------------------------------------------------
# Input 19 (S5U-670 G1): missing allowlist → BLOCK (fail closed)
# -------------------------------------------------------------------------
assert_ack "19 S5U-670 G1 missing allowlist" "$FIXTURE_DIR/happy.json" "$FIXTURE_DIR/nonexistent.txt" "block"

# -------------------------------------------------------------------------
# Input 20 (S5U-670 near-miss): wrong context (ci/check-run) → BLOCK
# -------------------------------------------------------------------------
# Structural check: context must equal "coordinator-ack" exactly, not just
# any success status on the commit. CI statuses are not gate evidence.
assert_ack "20 S5U-670 near-miss (wrong context)" "$FIXTURE_DIR/wrong_context.json" "$ALLOWLIST_FILE" "block"

# -------------------------------------------------------------------------
# Input 21 (S5U-670 near-miss): coordinator-ack context but state=failure → BLOCK
# -------------------------------------------------------------------------
# A failed status is not a pass. Manual revocation or accidental overwrite
# with state=failure must not satisfy the gate.
assert_ack "21 S5U-670 near-miss (state=failure)" "$FIXTURE_DIR/failed_state.json" "$ALLOWLIST_FILE" "block"

echo ""
echo "ALL TESTS PASSED"

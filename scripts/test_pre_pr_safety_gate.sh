#!/usr/bin/env bash
# S5U-647 / S5U-666 / S5U-670 / S5U-672 / S5U-673: smoke tests for the safety-gate
# scope probe in .claude/hooks/pre-pr-check.sh. Exercises three gate layers:
#
#   Layer 1 (S5U-647): regex over changed-file paths decides whether the probe fires
#     Inputs 1-12: happy / failure / adversarial regex coverage (pure-function)
#
#   Layer 2 (S5U-666): base-ref resolution (main vs origin/main vs fail-closed)
#     Inputs 13-14: missing-main-fails-closed, origin-main-fallback-succeeds
#                   (pure-function on a synthetic repo)
#
#   Layer 3 (S5U-670 / S5U-672 / S5U-673): coordinator-ack commit status.
#     Inputs 15-23: HARNESS spawns the REAL hook with `gh` shadowed via PATH
#                   and drives it against a throwaway branch in this repo.
#
# Run: bash scripts/test_pre_pr_safety_gate.sh
# Expected: "ALL TESTS PASSED" and exit 0.
#
# CI-wired under `python / test` (S5U-673 Gap 3). Local runs are still
# supported; the harness operates on the real repo root but isolates state
# via a namespaced throwaway branch and strict EXIT trap cleanup.
#
# S5U-673 changes (supersedes inline-replica approach from S5U-670):
#   - Coordinator-ack cases 15-23 now spawn the real hook under a mocked `gh`
#     instead of a replicated `validate_coordinator_ack()` function body.
#   - New input 22 (revocation: success-then-failure) validates the updated
#     "latest status wins" jq filter in the hook.
#   - New input 23 (re-affirmation: failure-then-success) exercises the
#     sort-latest branch in the PASS direction.
#   - Wired to CI: failure fails `python / test`.

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

HAPPY_PATHS="apps/pipeline/src/atr_pipeline/cli/run.py
apps/web/src/components/Foo.tsx
packages/schemas/python/models.py
docs/README.md"

run_case "happy path (pipeline + web + schemas + docs)" "$HAPPY_PATHS" "no"

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

FAILURE_PATHS_7=".claude/coordinator-signers.txt"
run_case "coordinator-signers.txt edit (S5U-670)" "$FAILURE_PATHS_7" "yes"

FAILURE_PATHS_8="scripts/test_pre_pr_safety_gate.sh"
run_case "test_pre_pr_safety_gate.sh edit (S5U-670)" "$FAILURE_PATHS_8" "yes"

ADV_PATHS_1="docs/hooks-overview.md
docs/safety-gate-policy.md"
run_case "docs about hooks (must NOT match)" "$ADV_PATHS_1" "no"

ADV_PATHS_2="scripts/export_to_web.py
scripts/bootstrap_extended_fixtures.py"
run_case "scripts/ non-check_*, non-pre-*" "$ADV_PATHS_2" "no"

ADV_PATHS_3=".claude/rules/pipeline.md
.claude/rules/web.md"
run_case ".claude/rules/ edits (must NOT match)" "$ADV_PATHS_3" "no"

ADV_PATHS_4=".claude/skills/ship/README.md"
run_case "non-SKILL.md file inside a skill dir" "$ADV_PATHS_4" "no"

ADV_PATHS_5="CLAUDE.md.bak"
run_case "CLAUDE.md.bak (not CLAUDE.md)" "$ADV_PATHS_5" "no"

MIXED_PATHS="apps/web/src/App.tsx
.claude/hooks/pre-commit-check.sh
apps/pipeline/src/foo.py"
run_case "mixed diff (triggers on hook)" "$MIXED_PATHS" "yes"

# =========================================================================
# Layer 2 (S5U-666): base-ref resolution (pure-function, synthetic repo)
# =========================================================================

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

TMPDIR_13=$(mktemp -d)
(
  cd "$TMPDIR_13"
  git init -q -b feature
  git config user.email "test@example.com"
  git config user.name "Test"
  git commit --allow-empty -q -m "initial"
  if resolve_base_ref >/dev/null 2>&1; then
    echo "FAIL [13 S5U-666 missing main+origin/main]: resolve_base_ref succeeded, expected failure"
    exit 1
  fi
)
if [ $? -ne 0 ]; then exit 1; fi
rm -rf "$TMPDIR_13"
echo "OK   [13 S5U-666 missing main+origin/main]: resolve_base_ref exits non-zero as expected"

TMPDIR_14=$(mktemp -d)
(
  cd "$TMPDIR_14"
  git init -q --bare origin.git
  git init -q --initial-branch=main work
  cd work
  git config user.email "test@example.com"
  git config user.name "Test"
  git commit --allow-empty -q -m "base"
  git remote add origin ../origin.git
  git push -q origin main
  git checkout -q -b feature
  git branch -q -D main
  git fetch -q origin
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
if [ $? -ne 0 ]; then exit 1; fi
rm -rf "$TMPDIR_14"
echo "OK   [14 S5U-666 origin/main fallback]: BASE=origin/main as expected"

# =========================================================================
# Layer 3 (S5U-670 / S5U-672 / S5U-673): coordinator-ack via REAL hook
# =========================================================================
#
# The harness spawns the real .claude/hooks/pre-pr-check.sh against a namespaced
# throwaway branch off main in THIS repo, with `gh` shadowed via PATH so the
# `gh api repos/.../commits/<sha>/statuses` call returns fixture JSON.
#
# Cleanup invariant (trap EXIT): original branch restored, throwaway branch
# deleted, probe file unlinked, stub tmp review artifact unlinked. The harness
# refuses to run if stash/switch operations fail.

HARNESS_PID=$$
FAKE_ISSUE="s5u-999${HARNESS_PID}"
THROWAWAY_BRANCH="s5unanow/${FAKE_ISSUE}-harness-probe"
PROBE_FILE=".claude/hooks/__harness_probe_${HARNESS_PID}.tmp"
REVIEW_FILE="tmp/review-${FAKE_ISSUE}.md"
MOCK_BIN=$(mktemp -d)
FIXTURE_DIR=$(mktemp -d)
ORIGINAL_BRANCH=$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD)

# Guard: working tree must be clean before we fabricate state. If the user has
# uncommitted changes, auto-stashing would mask real work on failure.
if ! (cd "$REPO_ROOT" && git diff --quiet && git diff --cached --quiet); then
  echo "FAIL [layer 3 harness]: working tree is dirty. Commit, stash, or discard"
  echo "  before running the coordinator-ack harness. The harness fabricates"
  echo "  state on a throwaway branch and refuses to run against a dirty tree."
  exit 1
fi

cleanup_harness() {
  local rc=$?
  set +e
  cd "$REPO_ROOT" 2>/dev/null || true
  # Restore original branch if we left it.
  local cur
  cur=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  if [ "$cur" != "$ORIGINAL_BRANCH" ] && [ -n "$ORIGINAL_BRANCH" ]; then
    git switch "$ORIGINAL_BRANCH" >/dev/null 2>&1 || true
  fi
  # Delete throwaway branch if it exists.
  if git show-ref --verify --quiet "refs/heads/$THROWAWAY_BRANCH"; then
    git branch -D "$THROWAWAY_BRANCH" >/dev/null 2>&1 || true
  fi
  # Remove fabricated artifacts (on original branch).
  rm -f "$REPO_ROOT/$PROBE_FILE" 2>/dev/null || true
  rm -f "$REPO_ROOT/$REVIEW_FILE" 2>/dev/null || true
  rm -rf "$MOCK_BIN" "$FIXTURE_DIR" 2>/dev/null || true
  set -e
  exit "$rc"
}
trap cleanup_harness EXIT

# Write the gh stub: for `gh api repos/.../commits/*/statuses`, read fixture
# from $MOCK_GH_FIXTURE and cat it. For any other invocation, fail with a
# diagnostic so we catch unexpected gh-use regressions (G1 fail-closed).
cat > "$MOCK_BIN/gh" <<'STUB_EOF'
#!/usr/bin/env bash
# Harness-mock gh for test_pre_pr_safety_gate.sh. Only the
# `api repos/.../commits/<sha>/statuses` form is supported; anything else
# is an unexpected call and is treated as a harness regression (exit 1).
if [ "${1:-}" = "api" ] && echo "${2:-}" | grep -qE '^repos/[^/]+/[^/]+/commits/[^/]+/statuses$'; then
  if [ -z "${MOCK_GH_FIXTURE:-}" ]; then
    echo "mock-gh: MOCK_GH_FIXTURE env var not set" >&2
    exit 1
  fi
  if [ ! -f "$MOCK_GH_FIXTURE" ]; then
    echo "mock-gh: fixture not found: $MOCK_GH_FIXTURE" >&2
    exit 1
  fi
  cat "$MOCK_GH_FIXTURE"
  exit 0
fi
echo "mock-gh: unsupported invocation: $*" >&2
exit 1
STUB_EOF
chmod +x "$MOCK_BIN/gh"

# Fixtures (mirror the inline ones from prior inputs 15-21 + new 22-23).
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
echo '[]' > "$FIXTURE_DIR/empty.json"
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
echo 'not valid json {' > "$FIXTURE_DIR/malformed.json"
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
# S5U-673: revocation — earlier success, later failure. New jq filter must
# select the LATEST by created_at and block.
cat > "$FIXTURE_DIR/revocation.json" <<'EOF'
[
  {
    "state": "success",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:00:00Z"
  },
  {
    "state": "failure",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:10:00Z"
  }
]
EOF
# S5U-673: re-affirmation — earlier failure, later success. New filter must
# select the latest (success) and pass.
cat > "$FIXTURE_DIR/reaffirm.json" <<'EOF'
[
  {
    "state": "failure",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:00:00Z"
  },
  {
    "state": "success",
    "context": "coordinator-ack",
    "creator": { "login": "s5unanow", "type": "User" },
    "created_at": "2026-04-20T12:10:00Z"
  }
]
EOF

# Fabricate a throwaway branch off main with a safety-gate-scoped probe file,
# so the hook's SAFETY_GATE_DIFF is non-empty and the coordinator-ack path fires.
cd "$REPO_ROOT"
# If main is not present locally (fresh clone edge case), fail cleanly.
if ! git rev-parse --verify main^{commit} >/dev/null 2>&1; then
  echo "FAIL [layer 3 harness]: local 'main' branch not present; cannot create"
  echo "  a throwaway branch. Run \`git fetch origin main:main\` first."
  exit 1
fi
# If the throwaway branch somehow exists, delete it defensively.
if git show-ref --verify --quiet "refs/heads/$THROWAWAY_BRANCH"; then
  git branch -D "$THROWAWAY_BRANCH" >/dev/null 2>&1
fi
git switch -c "$THROWAWAY_BRANCH" main >/dev/null 2>&1
echo "harness probe file for S5U-673 test harness (auto-cleaned)" > "$PROBE_FILE"
git add "$PROBE_FILE" >/dev/null
git -c user.email=harness@local -c user.name=harness commit -q -m "harness: probe for S5U-673 layer-3 tests"

# Write the review artifact that the hook reads. Must end with a valid verdict
# line and include structured fields. Must be newer than HEAD (touch to now).
mkdir -p "$REPO_ROOT/tmp"
cat > "$REPO_ROOT/$REVIEW_FILE" <<'EOF'
# Review artifact for harness self-test

This is a stub review artifact synthesized by scripts/test_pre_pr_safety_gate.sh
to exercise the pre-PR hook end-to-end. Do not commit.

## Verdict

Verdict: PASS

Critical: none
Warning: none
Suggestion: none
Probes run:
- harness probe 1
- harness probe 2
- harness probe 3
Bug IDs filed: none

**PASS**
EOF
# Ensure mtime is strictly newer than the throwaway HEAD commit timestamp.
# (The hook's staleness check is REVIEW_MTIME < HEAD_TIME; equality passes.)
touch "$REPO_ROOT/$REVIEW_FILE"

# invoke_hook: runs pre-pr-check.sh with $CLAUDE_TOOL_INPUT set + gh shadowed
# + fixture env var + a controlled PATH. Captures exit code + combined output.
# Echoes the exit code as the sole line on stdout (caller reads via $(...)),
# full output goes to $HARNESS_LOG.
HARNESS_LOG=$(mktemp)

invoke_hook() {
  local fixture="$1"
  local -; set +e
  MOCK_GH_FIXTURE="$fixture" \
  CLAUDE_TOOL_INPUT="gh pr create --title harness --body harness" \
  PATH="$MOCK_BIN:$PATH" \
    bash "$HOOK_SCRIPT" >"$HARNESS_LOG" 2>&1
  local rc=$?
  echo "$rc"
}

assert_hook() {
  local label="$1"
  local fixture="$2"
  local expect="$3"  # "pass" (exit 0) or "block" (exit non-zero)

  local rc
  rc=$(invoke_hook "$fixture")

  if [ "$rc" = "0" ]; then
    if [ "$expect" = "pass" ]; then
      echo "OK   [$label]: hook exited 0 as expected"
      grep -E '^(Review artifact verified|Coordinator-ack verified)' "$HARNESS_LOG" | sed 's/^/       /' || true
    else
      echo "FAIL [$label]: expected BLOCK (exit non-zero), got PASS (exit 0)"
      sed 's/^/       /' "$HARNESS_LOG"
      return 1
    fi
  else
    if [ "$expect" = "block" ]; then
      echo "OK   [$label]: hook exited $rc as expected"
      grep -E '^BLOCKED' "$HARNESS_LOG" | head -1 | sed 's/^/       /' || true
    else
      echo "FAIL [$label]: expected PASS (exit 0), got BLOCK (exit $rc)"
      sed 's/^/       /' "$HARNESS_LOG"
      return 1
    fi
  fi
}

echo ""
echo "Layer 3 harness: driving real hook against throwaway branch $THROWAWAY_BRANCH"
echo ""

# Input 15: happy — signed status → PASS
assert_hook "15 S5U-670 happy (signed status)" "$FIXTURE_DIR/happy.json" "pass"

# Input 16: empty status list → BLOCK
assert_hook "16 S5U-670 empty status list" "$FIXTURE_DIR/empty.json" "block"

# Input 17: worker self-posted → BLOCK
assert_hook "17 S5U-670 adversarial (worker self-post)" "$FIXTURE_DIR/wrong_creator.json" "block"

# Input 18: malformed JSON → BLOCK (G1)
assert_hook "18 S5U-670 G1 malformed JSON" "$FIXTURE_DIR/malformed.json" "block"

# Input 19: missing fixture file (simulates gh api failure: 404 / rate limit) → BLOCK
assert_hook "19 S5U-670 G1 gh api failure (missing fixture)" "$FIXTURE_DIR/nonexistent.json" "block"

# Input 20: wrong context (ci/check-run) → BLOCK
assert_hook "20 S5U-670 near-miss (wrong context)" "$FIXTURE_DIR/wrong_context.json" "block"

# Input 21: state=failure (single entry) → BLOCK
assert_hook "21 S5U-670 near-miss (state=failure)" "$FIXTURE_DIR/failed_state.json" "block"

# Input 22 (S5U-673 NEW): revocation — earlier success, later failure → BLOCK.
# Validates the updated jq filter that sorts by created_at and takes the latest.
assert_hook "22 S5U-673 revocation (success then failure)" "$FIXTURE_DIR/revocation.json" "block"

# Input 23 (S5U-673 NEW): re-affirmation — earlier failure, later success → PASS.
# Validates the sort-latest branch in the PASS direction.
assert_hook "23 S5U-673 re-affirmation (failure then success)" "$FIXTURE_DIR/reaffirm.json" "pass"

rm -f "$HARNESS_LOG"

# =========================================================================
# Layer 4 (S5U-672): COORDINATOR_ACK_STATUS_SOURCE env-var surface must be absent
# =========================================================================
ENV_VAR_HITS=$(grep -c 'COORDINATOR_ACK_STATUS_SOURCE' "$HOOK_SCRIPT" || true)
if [ "$ENV_VAR_HITS" -ne 0 ]; then
  echo "FAIL [24 S5U-672 env-var surface absent]: hook still references COORDINATOR_ACK_STATUS_SOURCE ($ENV_VAR_HITS hits)"
  grep -n 'COORDINATOR_ACK_STATUS_SOURCE' "$HOOK_SCRIPT" | sed 's/^/       /'
  echo "       This env var was the worker-controllable forgery surface — see tmp/plan-s5u-672.md."
  exit 1
fi
echo "OK   [24 S5U-672 env-var surface absent]: hook source has zero references to COORDINATOR_ACK_STATUS_SOURCE"

TEST_OVERRIDE_HITS=$(grep -c 'TEST OVERRIDE' "$HOOK_SCRIPT" || true)
if [ "$TEST_OVERRIDE_HITS" -ne 0 ]; then
  echo "FAIL [25 S5U-672 no test-override banner]: hook still prints 'TEST OVERRIDE' ($TEST_OVERRIDE_HITS hits)"
  grep -n 'TEST OVERRIDE' "$HOOK_SCRIPT" | sed 's/^/       /'
  echo "       The test-override code path was removed in S5U-672; re-adding it is a safety-gate regression."
  exit 1
fi
echo "OK   [25 S5U-672 no test-override banner]: hook does not print 'TEST OVERRIDE'"

echo ""
echo "ALL TESTS PASSED"

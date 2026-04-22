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
# Design (S5U-673): the harness spawns the real
# .claude/hooks/pre-pr-check.sh AGAINST THE CURRENT BRANCH without switching
# branches. The hook reads .claude/hooks/pre-pr-check.sh itself from disk; a
# `git switch` would revert the on-disk hook to the base branch's version,
# which is exactly the divergence the refactor is meant to expose. Staying
# on the current branch keeps the hook-under-test loaded with the pending
# changes.
#
# The current branch (s5unanow/s5u-<N>-…) typically already produces a
# non-empty `git diff --name-only main...HEAD` that matches the hook's
# safety-gate regex (hook edits, workflow edits, SKILL.md edits, etc.). On a
# branch whose diff is NOT safety-gate-scoped, the coordinator-ack branch of
# the hook never fires — the harness fails closed with a clear message rather
# than silently pass as "everything OK" (G1).
#
# `gh` is shadowed via PATH so `gh api …/statuses` returns fixture JSON. The
# harness temporarily relocates any real tmp/review-<issue>.md (to avoid
# interfering with an in-flight Path B review) and restores it on EXIT.

HARNESS_PID=$$
# `actions/checkout@v4` leaves HEAD detached on pull_request events (it checks
# out refs/pull/N/merge). The hook itself calls `git branch --show-current`,
# which returns empty in detached mode — so on CI we must materialize a local
# branch pointing at HEAD, named after the PR's source branch, so the hook can
# derive ISSUE_NUM from it.
#
# Resolution order:
#   1. $HARNESS_BRANCH_OVERRIDE (CI workflow passes github.head_ref)
#   2. `git rev-parse --abbrev-ref HEAD` (local dev branch)
DETECTED_BRANCH=$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -n "${HARNESS_BRANCH_OVERRIDE:-}" ]; then
  CUR_BRANCH="$HARNESS_BRANCH_OVERRIDE"
elif [ -n "$DETECTED_BRANCH" ] && [ "$DETECTED_BRANCH" != "HEAD" ]; then
  CUR_BRANCH="$DETECTED_BRANCH"
else
  # Detached HEAD with no override — cannot proceed.
  echo "FAIL [layer 3 harness]: detached HEAD with no HARNESS_BRANCH_OVERRIDE."
  echo "  Set HARNESS_BRANCH_OVERRIDE=<branch-name> or run from a named branch."
  exit 1
fi

# If we are in detached HEAD but have an override (CI pull_request case),
# create a local branch pointing at HEAD so the hook's `git branch --show-current`
# returns the expected name. Track for cleanup.
DETACHED_BRANCH_CREATED=""
if [ "$DETECTED_BRANCH" = "HEAD" ] || [ -z "$DETECTED_BRANCH" ]; then
  # We're in detached HEAD. Create a branch named $CUR_BRANCH at HEAD (if the
  # name is free). If the name already exists (shouldn't, on a fresh CI
  # checkout), point it at HEAD.
  if (cd "$REPO_ROOT" && git show-ref --verify --quiet "refs/heads/$CUR_BRANCH"); then
    (cd "$REPO_ROOT" && git branch -f "$CUR_BRANCH" HEAD)
  else
    (cd "$REPO_ROOT" && git branch "$CUR_BRANCH" HEAD)
  fi
  (cd "$REPO_ROOT" && git switch "$CUR_BRANCH" >/dev/null 2>&1)
  DETACHED_BRANCH_CREATED="$CUR_BRANCH"
fi

# S5U-691: grep pipeline must tolerate no-match (|| true). On main post-merge
# CI, CUR_BRANCH="main" contains no 's5u-<N>' substring; without `|| true`,
# `pipefail + set -e` would kill the script here before the skip-on-main
# branch below can fire. Option 1 of S5U-691 Fix sketch.
CUR_ISSUE_NUM=$(echo "$CUR_BRANCH" | grep -oiE 's5u-[0-9]+' | head -1 | tr '[:upper:]' '[:lower:]' || true)
REVIEW_FILE="tmp/review-${CUR_ISSUE_NUM}.md"
REVIEW_BACKUP="tmp/review-${CUR_ISSUE_NUM}.md.harness_backup_${HARNESS_PID}"
MOCK_BIN=$(mktemp -d)
FIXTURE_DIR=$(mktemp -d)

# Guard: working tree must be clean. The harness writes a stub review file
# and relies on deterministic mtime comparisons; uncommitted edits would
# interleave with the stub unpredictably.
if ! (cd "$REPO_ROOT" && git diff --quiet && git diff --cached --quiet); then
  echo "FAIL [layer 3 harness]: working tree is dirty. Commit, stash, or discard"
  echo "  before running the coordinator-ack harness. The harness writes a stub"
  echo "  tmp/review-<issue>.md in place (backing up any pre-existing file); a"
  echo "  dirty tree would make the backup/restore non-deterministic."
  exit 1
fi

# S5U-691 + S5U-696: empty-safety-gate-diff SKIP runs BEFORE the issue-number
# guard. Layer 3 requires a safety-gate-scoped diff vs main so the
# coordinator-ack branch of the hook fires. If the diff is empty of
# safety-gate paths, SKIP with exit 0 regardless of branch name:
#   - Post-merge CI on main: no diff against self; the gate was evaluated on
#     the PR that produced the merge (S5U-691).
#   - Non-safety-gate feature PR (pipeline-only, web-only, schemas-only,
#     docs-only): the coordinator-ack branch of the hook never fires on this
#     PR's own safety-gate review; there is nothing meaningful for layer 3
#     to exercise (S5U-696).
#
# Reorder rationale (S5U-691): the issue-number guard below used to run
# first, short-circuiting before the skip decision could fire. Putting the
# skip decision first makes both the main-post-merge and feature-branch
# cases exit 0 without depending on branch name matching s5u-<N>.
# Resolve a base ref — prefer local `main`, fall back to `origin/main` so CI
# runs on detached HEAD (where actions/checkout doesn't create a local main)
# also work. Fail closed if neither is present (G1).
HARNESS_BASE_REF=""
if (cd "$REPO_ROOT" && git rev-parse --verify main^{commit} >/dev/null 2>&1); then
  HARNESS_BASE_REF=main
elif (cd "$REPO_ROOT" && git rev-parse --verify origin/main^{commit} >/dev/null 2>&1); then
  HARNESS_BASE_REF=origin/main
else
  echo "FAIL [layer 3 harness]: neither 'main' nor 'origin/main' is resolvable; cannot compute safety-gate diff."
  exit 1
fi
SAFETY_DIFF_CHECK=$(cd "$REPO_ROOT" && git diff --name-only "$HARNESS_BASE_REF...HEAD" \
  | grep -E "$SAFETY_REGEX" || true)
# S5U-696: broaden the SKIP branch to any branch with no safety-gate diff,
# not just 'main'. The harness's job is to validate the coordinator-ack
# branch of the real pre-PR hook; a diff with no safety-gate paths has
# nothing for layer 3 to exercise regardless of branch name. Pre-S5U-696
# the SKIP was gated on CUR_BRANCH == 'main', which caused `python / test`
# to fail on every non-safety-gate feature PR (the overwhelming majority).
# See the S5U-588 CI-in-the-wild failure and the S5U-691 retrospective in
# tmp/plan-s5u-696.md §3.
#
# G1 invariants preserved: the upstream HARNESS_BASE_REF resolution fails
# closed on unresolvable main+origin/main, so a shallow-checkout
# environment cannot reach this SKIP; SAFETY_REGEX extraction fails closed
# at lines 47-50. The SKIP fires only when the diff against a resolvable
# base is genuinely empty of safety-gate paths.
if [ -z "$SAFETY_DIFF_CHECK" ]; then
  echo "SKIP [layer 3 harness]: branch '$CUR_BRANCH' has no safety-gate diff in main...HEAD."
  echo "  Nothing for the layer 3 harness to exercise — gate will be evaluated"
  echo "  on safety-gate PRs only. Layers 1 and 2 already passed above."
  echo ""
  echo "ALL TESTS PASSED"
  exit 0
fi

# Guard: harness needs an issue number in the branch name for the review-file
# lookup. Moved AFTER the skip-on-main branch (S5U-691 option 2) so main
# post-merge CI exits cleanly before reaching this guard.
if [ -z "$CUR_ISSUE_NUM" ]; then
  echo "FAIL [layer 3 harness]: current branch '$CUR_BRANCH' does not contain an"
  echo "  S5U-<N> issue number. The harness runs on the current branch so the"
  echo "  on-disk hook is the version under test; a non-namespaced branch cannot"
  echo "  drive the hook's review-file lookup deterministically."
  exit 1
fi

cleanup_harness() {
  local rc=$?
  set +e
  cd "$REPO_ROOT" 2>/dev/null || true
  # Restore the pre-existing review file if we backed it up. Otherwise we
  # wrote a net-new stub; remove it.
  if [ -f "$REPO_ROOT/$REVIEW_BACKUP" ]; then
    mv "$REPO_ROOT/$REVIEW_BACKUP" "$REPO_ROOT/$REVIEW_FILE" 2>/dev/null || true
  else
    rm -f "$REPO_ROOT/$REVIEW_FILE" 2>/dev/null || true
  fi
  # Detach + delete the ad-hoc branch we created for detached-HEAD CI runs.
  # `git switch --detach HEAD` puts us back into detached HEAD at the same
  # commit so `git branch -D` on the current branch succeeds.
  if [ -n "${DETACHED_BRANCH_CREATED:-}" ]; then
    git switch --detach HEAD >/dev/null 2>&1 || true
    git branch -D "$DETACHED_BRANCH_CREATED" >/dev/null 2>&1 || true
  fi
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

cd "$REPO_ROOT"

# Back up an in-flight Path B review artifact for this branch, if present.
# The harness writes a stub of its own; we restore the original on EXIT.
mkdir -p "$REPO_ROOT/tmp"
if [ -f "$REPO_ROOT/$REVIEW_FILE" ]; then
  mv "$REPO_ROOT/$REVIEW_FILE" "$REPO_ROOT/$REVIEW_BACKUP"
fi

# Write the stub review artifact. Must end with a valid verdict line and
# include the structured `Verdict:` / `Probes run:` fields. Must be newer
# than HEAD (`touch` to current time).
cat > "$REPO_ROOT/$REVIEW_FILE" <<'EOF'
# Review artifact for harness self-test

This is a stub review artifact synthesized by scripts/test_pre_pr_safety_gate.sh
to exercise the pre-PR hook end-to-end. Do not commit; the EXIT trap restores
any pre-existing review file and removes this stub.

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
# The hook's staleness check is REVIEW_MTIME < HEAD_TIME; `touch` now ensures
# mtime >= HEAD timestamp.
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
echo "Layer 3 harness: driving real hook on current branch $CUR_BRANCH (issue=$CUR_ISSUE_NUM)"
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

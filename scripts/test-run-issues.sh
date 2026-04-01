#!/usr/bin/env bash
# scripts/test-run-issues.sh — Integration test for run-issues.sh retry logic
#
# Creates a temporary directory with mock git/claude commands to simulate:
#   1. A successful issue (agent returns to main)
#   2. A stalled issue (agent stays on feature branch, /ship retry succeeds)
#   3. A stalled issue where retry also fails
#
# Usage:
#   ./scripts/test-run-issues.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Setup: fake git repo with a remote so git pull works
# ---------------------------------------------------------------------------
mkdir -p "$TEST_DIR/bin"

# Create repo with an initial commit, add scripts dir, set up remote
git init "$TEST_DIR/repo" --quiet
cd "$TEST_DIR/repo"
mkdir -p artifacts scripts
# Add a placeholder so scripts/ is tracked
touch scripts/.gitkeep
git add scripts/.gitkeep
git commit -m "init" --quiet

# Create a bare clone as remote, wire up tracking
git clone --bare "$TEST_DIR/repo" "$TEST_DIR/remote" --quiet
git remote add origin "$TEST_DIR/remote"
git fetch origin --quiet
git branch --set-upstream-to=origin/main main --quiet 2>/dev/null

# Copy the real script
cp "$SCRIPT_DIR/run-issues.sh" "$TEST_DIR/repo/scripts/run-issues.sh"

# ---------------------------------------------------------------------------
# Mock claude: simulates 3 issues
#   Issue 1: /next runs, agent returns to main (success)
#   Issue 2: /next runs, agent stays on feature branch; /ship retry succeeds
#   Issue 3: /next runs, agent stays on feature branch; /ship retry fails
# ---------------------------------------------------------------------------
CALL_LOG="$TEST_DIR/claude-calls.log"
touch "$CALL_LOG"

cat > "$TEST_DIR/bin/claude" << 'MOCK_CLAUDE'
#!/usr/bin/env bash
CALL_LOG="$(dirname "$0")/../claude-calls.log"
CALL_NUM=$(wc -l < "$CALL_LOG" | tr -d ' ')
CALL_NUM=$((CALL_NUM + 1))
echo "call=$CALL_NUM args=$*" >> "$CALL_LOG"

REPO_ROOT="$(git rev-parse --show-toplevel)"

case "$CALL_NUM" in
  1)
    # Smoke check: run-issues.sh verifies --max-turns is accepted
    echo "ok"
    ;;
  2)
    # Issue 1: /next — success, stay on main (simulates full ship)
    echo "[mock] Issue 1: /next completed, on main"
    ;;
  3)
    # Issue 2: /next — stall, create and stay on feature branch
    git checkout -b s5unanow/s5u-999-stalled-issue --quiet
    echo "[mock] Issue 2: /next stalled on feature branch"
    ;;
  4)
    # Issue 2: /ship retry — success, return to main
    git checkout main --quiet
    echo "[mock] Issue 2: /ship retry succeeded"
    ;;
  5)
    # Issue 3: /next — stall, create and stay on feature branch
    git checkout -b s5unanow/s5u-888-another-stall --quiet
    echo "[mock] Issue 3: /next stalled on feature branch"
    ;;
  6)
    # Issue 3: /ship retry — also fails, stay on branch
    echo "[mock] Issue 3: /ship retry also failed"
    ;;
esac
exit 0
MOCK_CLAUDE
chmod +x "$TEST_DIR/bin/claude"

# Put mock claude first in PATH
export PATH="$TEST_DIR/bin:$PATH"

# ---------------------------------------------------------------------------
# Run the script with 3 issues
# ---------------------------------------------------------------------------
echo "=== Running run-issues.sh with 3 mock issues ==="
echo ""

cd "$TEST_DIR/repo"
bash scripts/run-issues.sh 3

echo ""
echo "=== Validating results ==="

# Check the call log
TOTAL_CALLS=$(wc -l < "$CALL_LOG" | tr -d ' ')
echo "Total claude calls: $TOTAL_CALLS"

# Find the log file
LOG_FILE=$(ls "$TEST_DIR/repo/artifacts/run-issues-"*.log 2>/dev/null | head -1)
if [ -z "$LOG_FILE" ]; then
  echo "FAIL: No log file created"
  exit 1
fi

# Validate expected behavior
ERRORS=0

# Should have 6 claude calls: smoke check + /next x3 + /ship retry x2
if [ "$TOTAL_CALLS" -ne 6 ]; then
  echo "FAIL: Expected 6 claude calls, got $TOTAL_CALLS"
  ERRORS=$((ERRORS + 1))
else
  echo "PASS: 6 claude calls as expected (1 smoke + 3 /next + 2 /ship)"
fi

# Check log for shipped count
if grep -q "Shipped: 2/3" "$LOG_FILE"; then
  echo "PASS: Summary shows 2/3 shipped"
else
  echo "FAIL: Summary does not show 2/3 shipped"
  grep "Shipped:" "$LOG_FILE" || echo "(no Shipped line found)"
  ERRORS=$((ERRORS + 1))
fi

# Check log for the failed branch
if grep -q "s5unanow/s5u-888-another-stall" "$LOG_FILE"; then
  echo "PASS: Failed branch logged"
else
  echo "FAIL: Failed branch not logged"
  ERRORS=$((ERRORS + 1))
fi

# Check log for retry attempt
if grep -q "attempting /ship retry" "$LOG_FILE"; then
  echo "PASS: Retry attempts logged"
else
  echo "FAIL: No retry attempt logged"
  ERRORS=$((ERRORS + 1))
fi

# Verify --max-turns values passed correctly
if grep -q "max-turns 120" "$CALL_LOG"; then
  echo "PASS: --max-turns 120 passed to /next"
else
  echo "FAIL: --max-turns 120 not found in claude calls"
  ERRORS=$((ERRORS + 1))
fi

if grep -q "max-turns 20" "$CALL_LOG"; then
  echo "PASS: --max-turns 20 passed to /ship retry"
else
  echo "FAIL: --max-turns 20 not found in /ship retry calls"
  ERRORS=$((ERRORS + 1))
fi

# Should end on main
FINAL_BRANCH=$(git branch --show-current)
if [ "$FINAL_BRANCH" = "main" ]; then
  echo "PASS: Ended on main branch"
else
  echo "FAIL: Ended on $FINAL_BRANCH instead of main"
  ERRORS=$((ERRORS + 1))
fi

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "All tests passed!"
else
  echo "FAILED: $ERRORS test(s) failed"
  echo ""
  echo "--- Full log ---"
  cat "$LOG_FILE"
  exit 1
fi

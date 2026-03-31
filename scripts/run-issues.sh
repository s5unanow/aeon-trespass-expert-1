#!/usr/bin/env bash
# scripts/run-issues.sh — Autonomous issue runner (claude batch mode)
#
# Picks the next highest-priority unassigned Linear issue from the ATE1
# backlog, hands it to a fresh Claude Code agent via `/next`, and loops
# until the backlog is empty or the max-issues limit is reached.
#
# Each `claude -p` invocation is a clean agent — no context bleed between
# issues. Output is logged per-run to artifacts/ (gitignored).
#
# Post-issue verification: after each agent exits, the runner checks if
# the agent returned to main. If not, it retries shipping once via `/ship`.
# If the retry also fails, it logs the failure, returns to main, and
# continues to the next issue.
#
# Usage:
#   ./scripts/run-issues.sh          # process up to 10 issues (default)
#   ./scripts/run-issues.sh 5        # process up to 5 issues
#   ./scripts/run-issues.sh --dry-run        # print what would run, don't execute
#   ./scripts/run-issues.sh 5 --dry-run      # combine limit + dry-run
#
# Tip — fire and forget with tmux:
#   tmux new -s issues './scripts/run-issues.sh 20'

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
MAX_ISSUES=10
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *)
      if [[ "$arg" =~ ^[0-9]+$ ]] && [ "$arg" -ge 1 ]; then
        MAX_ISSUES="$arg"
      else
        echo "Usage: $0 [MAX_ISSUES] [--dry-run]" >&2
        exit 1
      fi
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="$REPO_ROOT/artifacts"
mkdir -p "$ARTIFACTS_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$ARTIFACTS_DIR/run-issues-$TIMESTAMP.log"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
  echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Tracking arrays (shipped / failed branch names)
# ---------------------------------------------------------------------------
shipped=()
failed=()

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
log "=== Autonomous issue runner started ==="
log "Max issues: $MAX_ISSUES | Dry run: $DRY_RUN"
log "Log file:   $LOG_FILE"
log ""

count=0

while [ "$count" -lt "$MAX_ISSUES" ]; do
  issue_num=$((count + 1))
  log "--- Picking issue #$issue_num of $MAX_ISSUES ---"

  if [ "$DRY_RUN" = true ]; then
    log "[dry-run] Would run: claude -p \"/next\" --dangerously-skip-permissions --max-turns 120"
    count=$((count + 1))
    log "[dry-run] Issue #$issue_num done (simulated)"
    log ""
    continue
  fi

  # Ensure we start from main with a clean state for each issue.
  # The /next skill handles branching, but we need to be on main first.
  cd "$REPO_ROOT"
  if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git status --porcelain)" ]; then
    log "!!! Dirty working tree detected — stashing before checkout"
    git stash push -m "run-issues: auto-stash before issue #$issue_num" --quiet
  fi
  git checkout main --quiet
  git pull --quiet

  # Run a fresh Claude agent. /next auto-picks the highest-priority
  # unassigned Backlog issue and runs the full workflow: branch -> implement
  # -> review -> PR -> merge -> update Linear.
  #
  # Disable pipefail so PIPESTATUS captures claude's exit code even when
  # piped through tee.
  set +o pipefail
  claude -p "/next" \
    --dangerously-skip-permissions \
    --max-turns 120 2>&1 | tee -a "$LOG_FILE"
  exit_code=${PIPESTATUS[0]}
  set -o pipefail

  count=$((count + 1))

  if [ "$exit_code" -ne 0 ]; then
    log "!!! Claude exited with code $exit_code on issue #$issue_num"

    # Unrecoverable infrastructure errors — don't waste cycles retrying
    if [ "$exit_code" -ge 126 ]; then
      log "!!! Exit code >= 126 (infrastructure failure) — stopping"
      failed+=("issue-$issue_num (exit $exit_code)")
      break
    fi
  fi

  # -----------------------------------------------------------------------
  # Post-issue verification: did the agent ship?
  #
  # If we're back on main, the full workflow completed (branch was deleted
  # after merge). If we're still on a feature branch, something stalled.
  # -----------------------------------------------------------------------
  current_branch="$(git branch --show-current)"

  if [ "$current_branch" = "main" ]; then
    log "Issue #$issue_num shipped (back on main)"
    shipped+=("issue-$issue_num")
  else
    log "[WARN] Still on $current_branch — attempting /ship retry"

    set +o pipefail
    claude -p "/ship" \
      --dangerously-skip-permissions \
      --max-turns 20 2>&1 | tee -a "$LOG_FILE"
    retry_exit=${PIPESTATUS[0]}
    set -o pipefail

    current_branch="$(git branch --show-current)"

    if [ "$current_branch" = "main" ]; then
      log "Issue #$issue_num shipped after retry"
      shipped+=("issue-$issue_num")
    else
      log "[ERROR] Issue #$issue_num did not ship after retry (branch: $current_branch, exit: $retry_exit)"
      failed+=("$current_branch")

      # Return to main so the next issue can start clean.
      # The repo may be in a conflict/rebase state, so abort those first.
      git rebase --abort 2>/dev/null || true
      git merge --abort 2>/dev/null || true
      if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git status --porcelain)" ]; then
        git stash push -m "run-issues: auto-stash failed issue on $current_branch" --quiet || \
          git checkout -- . 2>/dev/null || true
      fi
      git checkout main --quiet
      git pull --quiet
    fi
  fi

  log "--- Finished issue #$issue_num ---"
  log ""
done

# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------
log ""
log "=== Run summary ==="
log "Shipped: ${#shipped[@]}/${count}"
if [ ${#shipped[@]} -gt 0 ]; then
  log "  OK:     ${shipped[*]}"
fi
if [ ${#failed[@]} -gt 0 ]; then
  log "  Failed: ${failed[*]}"
fi
log "Full log: $LOG_FILE"

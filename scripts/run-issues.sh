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
    [0-9]*)    MAX_ISSUES="$arg" ;;
    *)
      echo "Usage: $0 [MAX_ISSUES] [--dry-run]" >&2
      exit 1
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
    log "[dry-run] Would run: claude -p \"/next\" --dangerously-skip-permissions --max-turns 60"
    count=$((count + 1))
    log "[dry-run] Issue #$issue_num done (simulated)"
    log ""
    continue
  fi

  # Ensure we start from main with a clean state for each issue.
  # The /next skill handles branching, but we need to be on main first.
  cd "$REPO_ROOT"
  git checkout main --quiet
  git pull --quiet

  # Run a fresh Claude agent. /next auto-picks the highest-priority
  # unassigned Backlog issue and runs the full workflow: branch -> implement
  # -> review -> PR -> merge -> update Linear.
  claude -p "/next" \
    --dangerously-skip-permissions \
    --max-turns 60 2>&1 | tee -a "$LOG_FILE"

  exit_code=${PIPESTATUS[0]}
  count=$((count + 1))

  if [ "$exit_code" -ne 0 ]; then
    log "!!! Claude exited with code $exit_code on issue #$issue_num — stopping"
    break
  fi

  log "--- Completed issue #$issue_num ---"
  log ""
done

log "=== Run complete: $count issue(s) processed ==="
log "Full log: $LOG_FILE"

#!/usr/bin/env bash
# Claude Code PreToolUse hook: ensure clean main before creating feature branches
# Receives CLAUDE_TOOL_INPUT as JSON with the Bash command
set -euo pipefail

# S5U-1247: normalize CR/LF to spaces (then squeeze whitespace runs) before the
# line-oriented trigger grep so a multi-line `git checkout -b` / `git switch -c`
# cannot straddle a line and skip the guard. This hook reads the RAW envelope (no
# `jq` decode), so the harness today JSON-escapes any newline (harmless no-op);
# this is defense-in-depth if a real newline ever reaches the input. The squeeze
# (`tr -s ' '`) collapses the resulting double-space so the multi-word substring
# trigger still matches. Sibling parity with pre-commit-check.sh.
TOOL_INPUT_ONELINE=$(printf '%s' "${CLAUDE_TOOL_INPUT:-}" | tr '\n\r' '  ' | tr -s ' ')

# Only intercept git checkout -b (branch creation)
if ! printf '%s' "$TOOL_INPUT_ONELINE" | grep -qE 'git checkout -b|git switch -c'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1

BRANCH=$(git branch --show-current)

# Only guard when branching FROM main
if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
  exit 0
fi

# Check for uncommitted changes
DIRTY=$(git status --porcelain 2>/dev/null)
if [ -n "$DIRTY" ]; then
  echo "BLOCKED: Working tree is dirty on '$BRANCH'. Clean up before creating a branch."
  echo ""
  echo "Uncommitted changes:"
  git status --short
  echo ""
  echo "Options:"
  echo "  1. git stash        -- stash changes, create branch, then git stash pop"
  echo "  2. git checkout .   -- discard changes (DESTRUCTIVE)"
  echo "  3. git add && git commit on a different branch first"
  exit 1
fi

# Check that main is up to date with remote
git fetch origin main --quiet 2>/dev/null || true
LOCAL=$(git rev-parse main 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "unknown")

if [ "$REMOTE" != "unknown" ] && [ "$LOCAL" != "$REMOTE" ]; then
  echo "WARNING: Local main is behind origin/main. Run 'git pull' first."
  echo "  Local:  $LOCAL"
  echo "  Remote: $REMOTE"
  echo ""
  echo "Proceeding anyway, but your branch may be based on stale code."
fi

echo "Main is clean. Creating feature branch."
exit 0

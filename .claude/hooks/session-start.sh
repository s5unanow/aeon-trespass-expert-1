#!/usr/bin/env bash
# Claude Code SessionStart hook: inject repo context at session start
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo /Users/s5una/projects/aeon-trespass-expert-1)"

# Current branch
BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
echo "Branch: $BRANCH"

# Extract Linear issue ID from branch name (s5unanow/s5u-XXX-...)
if [[ "$BRANCH" =~ s5u-([0-9]+) ]]; then
  echo "Issue: S5U-${BASH_REMATCH[1]}"
fi

# Dirty files (compact)
DIRTY=$(git status --porcelain 2>/dev/null)
if [ -n "$DIRTY" ]; then
  COUNT=$(echo "$DIRTY" | wc -l | tr -d ' ')
  echo "Dirty files ($COUNT):"
  echo "$DIRTY" | head -10
  if [ "$COUNT" -gt 10 ]; then
    echo "  ... and $((COUNT - 10)) more"
  fi
else
  echo "Working tree: clean"
fi

# Ahead/behind remote
UPSTREAM=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo "")
if [ -n "$UPSTREAM" ]; then
  AHEAD=$(git rev-list --count "$UPSTREAM..HEAD" 2>/dev/null || echo "0")
  BEHIND=$(git rev-list --count "HEAD..$UPSTREAM" 2>/dev/null || echo "0")
  if [ "$AHEAD" -gt 0 ] || [ "$BEHIND" -gt 0 ]; then
    echo "Remote: +${AHEAD}/-${BEHIND} vs $UPSTREAM"
  else
    echo "Remote: up to date with $UPSTREAM"
  fi
else
  echo "Remote: no upstream tracking"
fi

# Last 5 commits on current branch
echo "Recent commits:"
git log --oneline -5 2>/dev/null || echo "  (no commits)"

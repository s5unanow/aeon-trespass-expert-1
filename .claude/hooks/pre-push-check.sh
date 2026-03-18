#!/usr/bin/env bash
# Claude Code PreToolUse hook: block force pushes to main
set -euo pipefail

# Only intercept git push commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git push'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1

BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  if echo "$CLAUDE_TOOL_INPUT" | grep -qE 'force|--force|-f'; then
    echo "BLOCKED: Force push to '$BRANCH' is not allowed."
    exit 1
  fi
fi

echo "Push guard passed."
exit 0

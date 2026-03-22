#!/usr/bin/env bash
# Notification hook — sends macOS native notification when Claude finishes a task.
# No-ops on non-macOS platforms.

if [[ "$(uname -s)" != "Darwin" ]]; then
  exit 0
fi

msg="${CLAUDE_NOTIFICATION:-Task completed}"

osascript -e "display notification \"$(echo "$msg" | sed 's/["\]/\\&/g')\" with title \"Claude Code\""

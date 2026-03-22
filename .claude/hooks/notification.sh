#!/usr/bin/env bash
# Notification hook — sends macOS native notification when Claude finishes a task.
# No-ops on non-macOS platforms.

if [[ "$(uname -s)" != "Darwin" ]]; then
  exit 0
fi

if ! command -v jq &>/dev/null; then
  osascript -e 'display notification "Task completed" with title "Claude Code"'
  exit 0
fi

input=$(cat)
msg=$(echo "$input" | jq -r '.message // empty')
title=$(echo "$input" | jq -r '.title // empty')

msg="${msg:-Task completed}"
title="${title:-Claude Code}"

osascript -e "display notification \"$(echo "$msg" | sed 's/["\]/\\&/g')\" with title \"$(echo "$title" | sed 's/["\]/\\&/g')\""

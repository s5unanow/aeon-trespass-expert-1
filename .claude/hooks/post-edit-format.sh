#!/usr/bin/env bash
# Claude Code PostToolUse hook: auto-format files after Edit
# Receives CLAUDE_TOOL_INPUT as JSON with { file_path, old_string, new_string }
set -euo pipefail

# Extract file path from tool input JSON
FILE_PATH=$(echo "$CLAUDE_TOOL_INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"//;s/"$//')

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

case "$FILE_PATH" in
  *.py)
    OUTPUT=$(uv run ruff format "$FILE_PATH" 2>&1) || true
    if echo "$OUTPUT" | grep -q "1 file reformatted"; then
      echo "formatted: $(basename "$FILE_PATH")"
    fi
    ;;
  *.ts|*.tsx|*.css)
    BEFORE=$(md5 -q "$FILE_PATH")
    (cd /Users/s5una/projects/aeon-trespass-expert-1/apps/web && pnpm exec prettier --write "$FILE_PATH" > /dev/null 2>&1) || true
    AFTER=$(md5 -q "$FILE_PATH")
    if [ "$BEFORE" != "$AFTER" ]; then
      echo "formatted: $(basename "$FILE_PATH")"
    fi
    ;;
esac

exit 0

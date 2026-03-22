#!/usr/bin/env bash
# Claude Code PostToolUse hook: auto-format files after Edit
# Receives JSON on stdin with { tool_input: { file_path, old_string, new_string } }
set -euo pipefail

# Read JSON from stdin
input=$(cat)

# Extract file path — prefer jq, fall back to grep/sed
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$input" | jq -r '.tool_input.file_path // empty')
else
  FILE_PATH=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"//;s/"$//') || true
fi

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Portable checksum: shasum (available on macOS + Linux)
checksum() {
  shasum -a 256 "$1" | cut -d' ' -f1
}

# Resolve repo root dynamically
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")

case "$FILE_PATH" in
  *.py)
    OUTPUT=$(uv run ruff format "$FILE_PATH" 2>&1) || true
    if echo "$OUTPUT" | grep -q "1 file reformatted"; then
      echo "formatted: $(basename "$FILE_PATH")"
    fi
    ;;
  *.ts|*.tsx|*.css)
    if [ -z "$REPO_ROOT" ]; then
      exit 0
    fi
    BEFORE=$(checksum "$FILE_PATH")
    (cd "$REPO_ROOT/apps/web" && pnpm exec prettier --write "$FILE_PATH" > /dev/null 2>&1) || true
    AFTER=$(checksum "$FILE_PATH")
    if [ "$BEFORE" != "$AFTER" ]; then
      echo "formatted: $(basename "$FILE_PATH")"
    fi
    ;;
esac

exit 0

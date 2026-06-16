#!/usr/bin/env bash
# Claude Code PreToolUse hook: block force pushes to main
set -euo pipefail

# S5U-1247: normalize CR/LF to spaces (then squeeze whitespace runs) before the
# line-oriented trigger grep so a multi-line `git push` cannot straddle a line and
# skip the guard. This hook reads the RAW envelope (no `jq` decode), so the harness
# today JSON-escapes any newline and no real newline byte is present — making this a
# harmless no-op for current input AND defense-in-depth if a real newline ever
# reaches the input (pre-decoded `.command`, pretty-printed envelope, future harness
# change). The squeeze (`tr -s ' '`) collapses the resulting double-space so the
# multi-word substring `git push` still matches. Sibling parity with pre-commit-check.sh.
TOOL_INPUT_ONELINE=$(printf '%s' "${CLAUDE_TOOL_INPUT:-}" | tr '\n\r' '  ' | tr -s ' ')

# Only intercept git push commands
if ! printf '%s' "$TOOL_INPUT_ONELINE" | grep -q 'git push'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1

BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  if printf '%s' "$TOOL_INPUT_ONELINE" | grep -qE 'force|--force|-f'; then
    echo "BLOCKED: Force push to '$BRANCH' is not allowed."
    exit 1
  fi
fi

echo "Push guard passed."
exit 0

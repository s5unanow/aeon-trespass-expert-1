#!/usr/bin/env bash
# Claude Code PreToolUse hook: enforces branch discipline + quality gates before git commit
# Receives CLAUDE_TOOL_INPUT as JSON with the Bash command
set -euo pipefail

# Only intercept git commit commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git commit'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1

# -- Guard 1: Never commit on main --
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "BLOCKED: Direct commits to '$BRANCH' are not allowed."
  echo "Create a feature branch first: git checkout -b s5unanow/s5u-XXX-description"
  exit 1
fi

# -- Guard 2: Branch must follow Linear naming convention --
if ! echo "$BRANCH" | grep -qiE '^s5unanow/s5u-[0-9]+-'; then
  echo "BLOCKED: Branch '$BRANCH' does not follow naming convention."
  echo "Expected: s5unanow/s5u-<issue-number>-<description>"
  echo "Example:  s5unanow/s5u-42-add-retry-backoff"
  exit 1
fi

# Skip quality gates for amend (minor fixups, gates already passed on original commit)
if echo "$CLAUDE_TOOL_INPUT" | grep -q -- '--amend'; then
  echo "Branch guards passed (skipping quality gates for amend)."
  exit 0
fi

# -- Truncated output helper --
# Success: one-line summary. Failure: first 30 lines + count of truncated lines.
MAX_LINES=30

run_gate() {
  local label="$1"
  shift
  local output
  if output=$("$@" 2>&1); then
    echo "  ✓ $label"
    return 0
  else
    local total_lines
    total_lines=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
    if [ "$total_lines" -gt "$MAX_LINES" ]; then
      printf '%s\n' "$output" | head -"$MAX_LINES"
      echo "... ($((total_lines - MAX_LINES)) more lines truncated)"
    else
      printf '%s\n' "$output"
    fi
    echo ""
    echo "BLOCKED: $label failed."
    return 1
  fi
}

echo "Running pre-commit quality gates..."

run_gate "[1/8] ruff check" uv run ruff check . || exit 1
run_gate "[2/8] ruff format" uv run ruff format --check . || exit 1
run_gate "[3/8] mypy" uv run mypy apps/pipeline/src/ packages/schemas/python/ || exit 1
run_gate "[4/8] lint-imports" uv run lint-imports || exit 1
run_gate "[5/8] file length" uv run python scripts/check_file_length.py || exit 1
run_gate "[6/8] eslint" bash -c "cd apps/web && pnpm lint" || exit 1
run_gate "[7/8] tsc" bash -c "cd apps/web && pnpm typecheck" || exit 1
run_gate "[8/8] pytest" uv run pytest -x -q --timeout=60 -m "not slow" || exit 1

echo "All quality gates passed."
exit 0

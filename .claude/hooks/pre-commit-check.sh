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

echo "Running pre-commit quality gates..."

# Gate 1: ruff check
echo "  [1/8] ruff check..."
if ! uv run ruff check . 2>&1; then
  echo ""
  echo "BLOCKED: ruff check failed. Fix lint errors before committing."
  exit 1
fi

# Gate 2: ruff format
echo "  [2/8] ruff format --check..."
if ! uv run ruff format --check . 2>&1; then
  echo ""
  echo "BLOCKED: ruff format failed. Run 'ruff format' to fix."
  exit 1
fi

# Gate 3: mypy
echo "  [3/8] mypy..."
if ! uv run mypy apps/pipeline/src/ packages/schemas/python/ 2>&1; then
  echo ""
  echo "BLOCKED: mypy failed. Fix type errors before committing."
  exit 1
fi

# Gate 4: import layer contracts
echo "  [4/8] lint-imports..."
if ! uv run lint-imports 2>&1; then
  echo ""
  echo "BLOCKED: Import layer contracts violated. Fix imports before committing."
  exit 1
fi

# Gate 5: file length check
echo "  [5/8] check file length..."
if ! uv run python scripts/check_file_length.py 2>&1; then
  echo ""
  echo "BLOCKED: File length limit exceeded. Split long files before committing."
  exit 1
fi

# Gate 6: eslint (frontend)
echo "  [6/8] eslint..."
if ! (cd apps/web && pnpm lint 2>&1); then
  echo ""
  echo "BLOCKED: ESLint failed. Fix frontend lint errors before committing."
  exit 1
fi

# Gate 7: tsc
echo "  [7/8] tsc..."
if ! (cd apps/web && pnpm typecheck 2>&1); then
  echo ""
  echo "BLOCKED: tsc failed. Fix TypeScript errors before committing."
  exit 1
fi

# Gate 8: pytest (fail-fast, skip slow integration tests)
echo "  [8/8] pytest (fast)..."
if ! uv run pytest -x -q --timeout=60 -m "not slow" 2>&1; then
  echo ""
  echo "BLOCKED: Tests failed. Fix failing tests before committing."
  exit 1
fi

echo "All quality gates passed."
exit 0

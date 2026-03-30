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

# -- Gate 0: Credential & secret guard --
# Scans staged files for secrets before any other quality gate.
SECRETS_FOUND=0

# 0a. Filename patterns — block dangerous file types
STAGED_FILES=$(git diff --cached --name-only)
if [ -n "$STAGED_FILES" ]; then
  DANGEROUS_FILES=$(echo "$STAGED_FILES" \
    | grep -E '(^|/)\.env$|(^|/)\.env\.[^/]+$|\.key$|\.pem$|(^|/)credentials\.json$|(^|/)secrets\.[^/]+$|\.secret$' \
    | grep -vE '\.(example|template)$' || true)
  if [ -n "$DANGEROUS_FILES" ]; then
    echo "BLOCKED: Staged files match secret/credential filename patterns:"
    echo "$DANGEROUS_FILES" | sed 's/^/  /'
    SECRETS_FOUND=1
  fi
fi

# 0b. Content patterns — detect API keys/secrets in added lines of staged diffs
# Exclude this hook file to avoid self-matching on pattern strings.
CONTENT_MATCHES=$(git diff --cached -U0 -- . ':!.claude/hooks/pre-commit-check.sh' \
  | grep -E '^\+' | grep -vE '^\+\+\+' \
  | grep -E 'sk-[a-zA-Z0-9_-]{8,}|AKIA[0-9A-Z]{8,}|ghp_[a-zA-Z0-9]{8,}|gho_[a-zA-Z0-9]{8,}|-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----' \
  || true)
if [ -n "$CONTENT_MATCHES" ]; then
  echo "BLOCKED: Staged diffs contain potential secrets:"
  echo "$CONTENT_MATCHES" | head -10 | sed 's/^/  /'
  SECRETS_FOUND=1
fi

if [ "$SECRETS_FOUND" -ne 0 ]; then
  echo ""
  echo "If this is a false positive, unstage the file or add to an allowlist."
  exit 1
fi
echo "  ✓ [0/9] secret guard"

# -- Advisory: schema model change reminder --
SCHEMA_MODELS_STAGED=$(git diff --cached --name-only -- 'packages/schemas/python/' | grep '\.py$' || true)
if [ -n "$SCHEMA_MODELS_STAGED" ]; then
  echo "  ⚠ Schema models changed — run 'make codegen' if you haven't already"
fi

run_gate "[1/9] ruff check" uv run ruff check . || exit 1
run_gate "[2/9] ruff format" uv run ruff format --check . || exit 1
run_gate "[3/9] mypy" uv run mypy apps/pipeline/src/ packages/schemas/python/ || exit 1
run_gate "[4/9] lint-imports" uv run lint-imports || exit 1
run_gate "[5/9] file length" uv run python scripts/check_file_length.py || exit 1
run_gate "[6/9] oxlint" bash -c "cd apps/web && pnpm lint" || exit 1
run_gate "[7/9] tsc" bash -c "cd apps/web && pnpm typecheck" || exit 1
run_gate "[8/9] pytest" uv run pytest -x -q --timeout=60 -m "not slow" || exit 1

echo "All quality gates passed."
exit 0

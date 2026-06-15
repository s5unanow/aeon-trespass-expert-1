#!/usr/bin/env bash
# Claude Code PreToolUse hook: enforces branch discipline + quality gates before git commit
# Receives CLAUDE_TOOL_INPUT as JSON with the Bash command
set -euo pipefail

# Extract the Bash command from the JSON envelope. jq is an established hard
# dependency of the hook stack (pre-pr-check.sh fails closed without it); if it
# is somehow absent we fall back to scanning the raw envelope, which is
# fail-closed for the trigger (more likely to TRIGGER, never to skip a commit).
COMMAND=""
if command -v jq >/dev/null 2>&1; then
  COMMAND=$(printf '%s' "${CLAUDE_TOOL_INPUT:-}" \
    | jq -r '.command // .tool_input.command // empty' 2>/dev/null || true)
fi
# Empty extraction (jq missing, no .command field, or malformed JSON): fall back
# to the raw envelope so a git-commit buried in malformed input is still caught.
if [ -z "$COMMAND" ]; then
  COMMAND="${CLAUDE_TOOL_INPUT:-}"
fi

# Only intercept git commit commands. Flag-tolerant: the literal substring
# `grep -q 'git commit'` was defeated by any flag between `git` and `commit`
# (`git -C <p> commit`, `git --no-pager commit`, `git -c k=v commit`). We match
# the word `git` preceding the word `commit` so every flag form is caught. The
# accepted residual is the inverse FP — a command that merely *mentions* both
# words (e.g. `echo "how to git commit"`) also triggers; closing FN vectors is
# the goal, not eliminating that pre-existing FP (see plans/002).
if ! printf '%s' "$COMMAND" | grep -qE '\bgit\b.*\bcommit\b'; then
  exit 0
fi

# Resolve the repo root from the harness env (set for hooks) with a git
# fallback for manual invocation. This makes the hook validate the tree being
# committed in any worktree / second clone, not a hardcoded primary checkout.
# G1: if neither resolves (not in a repo), git rev-parse fails and
# `set -euo pipefail` aborts non-zero — fail-closed, correct for a commit gate.
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

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

# NOTE: the `--amend` quality-gate skip is intentionally positioned AFTER Gate 0
# (the secret/credential scan) below. An amend can stage arbitrary new content
# (a fresh .env, an sk- key), so the secret scan must run unconditionally; only
# the slower quality gates 1-8 are skipped for amends. See plans/002.

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

# Skip the slower quality gates (1-8) for amends — gates already passed on the
# original commit and amends are typically minor fixups. Gate 0 (above) has
# already scanned any newly staged content, so a secret introduced by the amend
# is still blocked. The branch guards and secret scan ran unconditionally.
if printf '%s' "$COMMAND" | grep -q -- '--amend'; then
  echo "Branch guards + secret scan passed (skipping quality gates 1-8 for amend)."
  exit 0
fi

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

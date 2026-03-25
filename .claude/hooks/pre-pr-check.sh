#!/usr/bin/env bash
# Claude Code PreToolUse hook: block PR creation without review agent artifact
set -euo pipefail

# Only intercept gh pr create commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'gh pr create'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1

BRANCH=$(git branch --show-current)

# Extract issue number from branch name (s5unanow/s5u-<NUMBER>-description)
ISSUE_NUM=$(echo "$BRANCH" | grep -oiE 's5u-[0-9]+' | head -1 | tr '[:upper:]' '[:lower:]')

if [ -z "$ISSUE_NUM" ]; then
  echo "WARNING: Could not extract issue number from branch '$BRANCH'. Skipping review check."
  exit 0
fi

REVIEW_FILE="tmp/review-${ISSUE_NUM}.md"

if [ ! -f "$REVIEW_FILE" ]; then
  echo "BLOCKED: No review artifact found at '$REVIEW_FILE'."
  echo ""
  echo "You MUST run the review agent before creating a PR."
  echo "Read .claude/prompts/review.md and spawn a review agent, or use /ship which includes review."
  echo ""
  echo "The review agent will save its output to '$REVIEW_FILE'."
  exit 1
fi

# Verify the review contains a verdict (ensures it actually completed)
if ! grep -qE '\*\*(BLOCK|PASS WITH WARNINGS|PASS)\*\*' "$REVIEW_FILE"; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' exists but contains no verdict."
  echo "The review must end with **BLOCK**, **PASS WITH WARNINGS**, or **PASS**."
  exit 1
fi

# Block if the verdict is BLOCK
if grep -qE '\*\*BLOCK\*\*' "$REVIEW_FILE" && ! grep -qE '\*\*PASS' "$REVIEW_FILE"; then
  echo "BLOCKED: Review verdict is BLOCK. Fix the issues before creating a PR."
  echo ""
  cat "$REVIEW_FILE"
  exit 1
fi

echo "Review artifact verified: $REVIEW_FILE"
exit 0

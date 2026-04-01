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
if grep -qE '\*\*BLOCK\*\*' "$REVIEW_FILE"; then
  echo "BLOCKED: Review verdict is BLOCK. Fix the issues before creating a PR."
  echo ""
  cat "$REVIEW_FILE"
  exit 1
fi

echo "Review artifact verified: $REVIEW_FILE"

# --- Conditional Codex review enforcement ---
# Primary: marker file (written by /ship or /codex-review skills).
# Fallback: query Linear API directly for cross-system-review label.
CODEX_MARKER="tmp/.codex-required-${ISSUE_NUM}"
CODEX_REQUIRED=false

if [ -f "$CODEX_MARKER" ]; then
  CODEX_REQUIRED=true
else
  # No marker — query Linear API independently
  # Source project .env if LINEAR_API_KEY not already in env
  if [ -z "${LINEAR_API_KEY:-}" ] && [ -f .env ]; then
    # shellcheck disable=SC1091
    set +u; source .env; set -u
  fi

  if [ -z "${LINEAR_API_KEY:-}" ]; then
    echo "WARNING: No marker file and LINEAR_API_KEY not set."
    echo "Cannot verify cross-system-review label on Linear issue."
    echo "Set LINEAR_API_KEY in .env for full safety coverage."
  else
    ISSUE_NUMBER=$(echo "$ISSUE_NUM" | grep -oE '[0-9]+')
    LINEAR_RESPONSE=$(curl -s --max-time 5 \
      -X POST \
      -H "Content-Type: application/json" \
      -H "Authorization: $LINEAR_API_KEY" \
      -d "{\"query\": \"{ issues(filter: { number: { eq: $ISSUE_NUMBER }, team: { key: { eq: \\\"S5U\\\" } } }) { nodes { labels { nodes { name } } } } }\"}" \
      https://api.linear.app/graphql 2>/dev/null || true)

    if [ -n "$LINEAR_RESPONSE" ]; then
      LABEL_MATCH=$(echo "$LINEAR_RESPONSE" | jq -r \
        '.data.issues.nodes[0].labels.nodes[]?.name // empty' 2>/dev/null \
        | grep -c 'cross-system-review' || true)
      if [ "$LABEL_MATCH" -gt 0 ]; then
        CODEX_REQUIRED=true
        echo "Linear API: cross-system-review label detected on ${ISSUE_NUM}."
      fi
    else
      echo "WARNING: Linear API unreachable (timeout or error)."
      echo "Marker-file fallback only. Cannot confirm label status."
    fi
  fi
fi

if [ "$CODEX_REQUIRED" = true ]; then
  CODEX_FILE="tmp/codex-review-${ISSUE_NUM}.md"

  if [ ! -f "$CODEX_FILE" ]; then
    echo "BLOCKED: Codex review required (cross-system-review label) but no artifact at '$CODEX_FILE'."
    echo ""
    echo "Run /codex-review or use /ship which includes conditional Codex review."
    exit 1
  fi

  if ! grep -q 'verdict: APPROVED' "$CODEX_FILE"; then
    echo "BLOCKED: Codex review artifact exists but verdict is not APPROVED."
    echo ""
    echo "Address Codex feedback and re-run the review."
    exit 1
  fi

  echo "Codex review artifact verified: $CODEX_FILE"
fi

# --- Advisory visual verification check ---
# If the branch touches rendering paths (components, styles, render stages),
# check for recent screenshot artifacts in tmp/. Advisory only — exit 0 regardless.

RENDER_PATHS=$(git diff --name-only main...HEAD -- \
  'apps/web/src/components/' \
  'apps/web/src/routes/' \
  'apps/web/src/styles/' \
  'scripts/export_to_web.py' \
  'scripts/_export_blocks.py' \
  'apps/pipeline/src/atr_pipeline/stages/render/' 2>/dev/null || true)

if [ -n "$RENDER_PATHS" ]; then
  # Check for PNG screenshots in tmp/ modified within the last 2 hours
  SCREENSHOTS=$(find tmp/ -maxdepth 1 -name '*.png' -mmin -120 2>/dev/null | head -1)

  if [ -z "$SCREENSHOTS" ]; then
    echo ""
    echo "WARNING: Rendering changes detected but no visual verification screenshots in tmp/."
    echo "Consider running visual verification before PR."
    echo "Changed rendering files:"
    echo "$RENDER_PATHS" | sed 's/^/  /'
    echo ""
  fi
fi

# --- Advisory extraction scope + golden refresh check ---
# Runs check_extraction_scope.py to detect extraction-related changes.
# If extraction scope is detected but no golden refresh commit is found, warns the user.
# Advisory only — never blocks PR creation.

SCOPE_JSON=$(cd /Users/s5una/projects/aeon-trespass-expert-1 && uv run python scripts/check_extraction_scope.py --base main --head HEAD 2>/dev/null || true)

if [ -n "$SCOPE_JSON" ]; then
  # check_extraction_scope.py outputs indented JSON — "areas": [] means no extraction scope
  if ! echo "$SCOPE_JSON" | grep -q '"areas": \[\]'; then
    # Extraction scope detected — extract area names for the warning message
    AREAS=$(echo "$SCOPE_JSON" | python3 -c "import sys,json; print(','.join(json.load(sys.stdin).get('areas',[])))" 2>/dev/null || echo "unknown")
    GOLDEN_DETECTED=$(echo "$SCOPE_JSON" | grep -c '"golden_refresh_detected": true' || true)

    if [ "$GOLDEN_DETECTED" -eq 0 ]; then
      # Check if any commit on this branch has "refresh goldens" in its message
      HAS_REFRESH=$(git log main..HEAD --format='%s' | grep -ic 'refresh goldens' || true)

      if [ "$HAS_REFRESH" -eq 0 ]; then
        echo ""
        echo "WARNING: Extraction scope detected (areas: $AREAS) but no golden refresh commit found."
        echo "CI will likely fail — consider running golden refresh before pushing."
        echo ""
      fi
    fi
  fi
fi

exit 0

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

# S5U-613: verdict must be the last non-blank line of the file, not embedded
# in prose. The review prompt explicitly requires the final-line placement;
# locating the verdict this way prevents backtick-quoted or referenced
# strings inside findings (e.g., `**BLOCK**` in a sentence) from flipping
# the gate (plan-s5u-613.md scenario D).
FINAL_LINE=$(grep -vE '^[[:space:]]*$' "$REVIEW_FILE" | tail -1)

if ! echo "$FINAL_LINE" | grep -qE '^\*\*(BLOCK|PASS WITH WARNINGS|PASS)\*\*[[:space:]]*$'; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' does not end with a valid verdict line."
  echo ""
  echo "The final non-blank line must be exactly one of:"
  echo "  **PASS**"
  echo "  **PASS WITH WARNINGS**"
  echo "  **BLOCK**"
  echo ""
  echo "Found: $FINAL_LINE"
  exit 1
fi

if echo "$FINAL_LINE" | grep -qE '^\*\*BLOCK\*\*[[:space:]]*$'; then
  echo "BLOCKED: Review verdict is BLOCK. Fix the issues before creating a PR."
  echo ""
  cat "$REVIEW_FILE"
  exit 1
fi

# --- S5U-613: structured verdict contract enforcement ---
# The review prompt now requires a structured verdict block with Verdict: and
# Probes run: fields. This guards against fabricated or template artifacts
# (see plan-s5u-613.md scenario B) and confirms the reviewer actually ran
# concrete checks rather than rubber-stamping.

if ! grep -qE '^Verdict:[[:space:]]+(PASS|PASS WITH WARNINGS|BLOCK)' "$REVIEW_FILE"; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' is missing the structured 'Verdict:' field."
  echo ""
  echo "The review must include a structured verdict block matching the"
  echo "contract in .claude/prompts/review.md (## Verdict section with"
  echo "'Verdict:', 'Probes run:', etc.)."
  exit 1
fi

if ! grep -qE '^Probes run:' "$REVIEW_FILE"; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' is missing the 'Probes run:' field."
  echo ""
  echo "The reviewer must enumerate the concrete probes they ran (files read,"
  echo "commands executed, success criteria tested). An empty audit trail means"
  echo "an unsubstantiated review — block it."
  exit 1
fi

# Count probe bullets (lines starting with '- ' after the 'Probes run:' header).
# Require at least 3 — fewer signals a perfunctory review.
PROBE_COUNT=$(awk '
  /^Probes run:/ { in_probes = 1; next }
  in_probes && /^[A-Za-z].*:/ { in_probes = 0 }
  in_probes && /^-[[:space:]]+[^[:space:]]/ { count++ }
  END { print count + 0 }
' "$REVIEW_FILE")

if [ "$PROBE_COUNT" -lt 3 ]; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' lists only $PROBE_COUNT probe(s) (need >=3)."
  echo ""
  echo "The 'Probes run:' section must enumerate at least 3 concrete checks."
  echo "This is the audit trail that distinguishes a real review from a stub."
  exit 1
fi

# --- S5U-619: structured Verdict: field must agree with final-line token ---
# The hook previously validated the two verdict locations independently. An
# artifact stating `Verdict: BLOCK` in the structured field with `**PASS**` as
# its final non-blank line would pass the gate — either a copy-paste error
# flipping BLOCK to PASS, or a deliberate bypass that looks innocent because
# the structured block appears correct. Extract both tokens and require
# byte-equality; disagreement is a hard block.
FIELD_VERDICT=$(grep -E '^Verdict:[[:space:]]+(PASS|PASS WITH WARNINGS|BLOCK)' "$REVIEW_FILE" \
  | head -1 \
  | sed -E 's/^Verdict:[[:space:]]+//; s/[[:space:]]+$//')
FINAL_VERDICT=$(echo "$FINAL_LINE" | sed -E 's/^\*\*(.*)\*\*[[:space:]]*$/\1/')
if [ "$FIELD_VERDICT" != "$FINAL_VERDICT" ]; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' has disagreeing verdicts."
  echo ""
  echo "  Structured 'Verdict:' field: $FIELD_VERDICT"
  echo "  Final-line '**...**' token:  $FINAL_VERDICT"
  echo ""
  echo "The two locations must name the same verdict. Either the reviewer"
  echo "typo'd one of them, or the artifact is a bypass attempt. Fix the"
  echo "review artifact so both locations agree, then retry."
  exit 1
fi

# --- S5U-613: staleness check ---
# Reject artifacts whose mtime predates the branch's HEAD commit. This guards
# against reviews conducted at an earlier commit that no longer reflect the
# shipped diff (see plan-s5u-613.md scenario C).

HEAD_TIME=$(git log -1 --format=%ct HEAD 2>/dev/null || echo 0)
# Portable mtime: Linux uses -c %Y, BSD/macOS uses -f %m.
REVIEW_MTIME=$(stat -c %Y "$REVIEW_FILE" 2>/dev/null || stat -f %m "$REVIEW_FILE" 2>/dev/null || echo 0)

if [ "$HEAD_TIME" -gt 0 ] && [ "$REVIEW_MTIME" -gt 0 ] && [ "$REVIEW_MTIME" -lt "$HEAD_TIME" ]; then
  echo "BLOCKED: Review artifact '$REVIEW_FILE' is stale."
  echo ""
  echo "  Review mtime:  $REVIEW_MTIME"
  echo "  HEAD commit:   $HEAD_TIME"
  echo ""
  echo "The review was written before the latest commit on this branch, which"
  echo "means it did not inspect the code you are about to ship. Re-run the"
  echo "review agent to regenerate the artifact at HEAD."
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
  elif ! command -v jq >/dev/null 2>&1; then
    echo "WARNING: jq not found. Cannot parse Linear API response."
    echo "Install jq for full safety coverage."
  else
    # Extract numeric part only: s5u-467 -> 467 (sed avoids matching '5' in 's5u')
    ISSUE_NUMBER=$(echo "$ISSUE_NUM" | sed 's/^s5u-//')
    LINEAR_RESPONSE=$(curl -s --max-time 5 \
      -X POST \
      -H "Content-Type: application/json" \
      -H "Authorization: $LINEAR_API_KEY" \
      -d "{\"query\": \"{ issues(filter: { number: { eq: $ISSUE_NUMBER }, team: { key: { eq: \\\"S5U\\\" } } }) { nodes { labels { nodes { name } } } } }\"}" \
      https://api.linear.app/graphql 2>/dev/null || true)

    if [ -n "$LINEAR_RESPONSE" ]; then
      # Check for API-level errors (expired key, auth failure, etc.)
      HAS_DATA=$(echo "$LINEAR_RESPONSE" | jq -e '.data.issues.nodes[0]' >/dev/null 2>&1 && echo 1 || echo 0)
      if [ "$HAS_DATA" -eq 0 ]; then
        echo "WARNING: Linear API returned an error or unexpected response."
        echo "Marker-file fallback only. Cannot confirm label status."
      else
        LABEL_MATCH=$(echo "$LINEAR_RESPONSE" | jq -r \
          '.data.issues.nodes[0].labels.nodes[]?.name // empty' 2>/dev/null \
          | grep -c 'cross-system-review' || true)
        if [ "$LABEL_MATCH" -gt 0 ]; then
          CODEX_REQUIRED=true
          echo "Linear API: cross-system-review label detected on ${ISSUE_NUM}."
        fi
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

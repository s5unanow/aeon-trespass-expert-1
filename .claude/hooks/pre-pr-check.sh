#!/usr/bin/env bash
# Claude Code PreToolUse hook: block PR creation without review agent artifact
set -euo pipefail

# Only intercept gh pr create commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'gh pr create'; then
  exit 0
fi

# Resolve the repo root dynamically so the hook is portable. When Claude Code
# invokes this hook locally, the CWD is typically the worker's repo root
# already; `git rev-parse --show-toplevel` gives us the authoritative answer.
# S5U-673 made this dynamic because the CI harness
# (scripts/test_pre_pr_safety_gate.sh) needs to spawn this hook on GitHub
# Actions runners where /Users/s5una/... obviously does not exist. The
# previous hardcoded path was a portability bug; we fall back to it only as
# a last resort for worker environments without a git CWD.
if REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  cd "$REPO_ROOT"
elif [ -d /Users/s5una/projects/aeon-trespass-expert-1 ]; then
  cd /Users/s5una/projects/aeon-trespass-expert-1
else
  echo "BLOCKED: pre-pr-check.sh cannot locate the repo root."
  echo "  Not a git repo (CWD=$(pwd)) and no fallback path available."
  exit 1
fi

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

# --- S5U-666: fail-closed base-ref resolution ---
# Prior implementation ran `git diff main...HEAD 2>/dev/null | ... || true`,
# which silently produced an empty diff if the local `main` branch did not
# exist (fresh clone, worktree from origin/main, branch renamed, etc.). The
# empty diff caused the safety-gate probe to skip entirely, reproducing the
# exact bypass S5U-647 was filed to close.
#
# Per .claude/rules/guards.md Rule G1 (fail-closed defaults): a guard without
# the state it needs must exit non-zero, never silently pass. Resolve the base
# ref explicitly, fall through to origin/main, and BLOCK if neither resolves.
resolve_base_ref() {
  if git rev-parse --verify main^{commit} >/dev/null 2>&1; then
    echo main
    return 0
  fi
  if git rev-parse --verify origin/main^{commit} >/dev/null 2>&1; then
    echo origin/main
    return 0
  fi
  return 1
}

if ! BASE_REF=$(resolve_base_ref); then
  echo "BLOCKED: pre-pr-check.sh cannot resolve a base ref."
  echo ""
  echo "Tried 'main' and 'origin/main'; neither is present in this working"
  echo "tree. This usually means a shallow checkout, a detached worktree,"
  echo "or a clone without the main branch fetched. The safety-gate scope"
  echo "probe cannot run without a base ref."
  echo ""
  echo "Per .claude/rules/guards.md Rule G1, a guard without the state it"
  echo "needs fails closed. Re-run after fetching origin/main:"
  echo "  git fetch origin main:main"
  echo ""
  echo "Failing closed per S5U-666 (supersedes the silent-empty behavior"
  echo "that reproduced the S5U-647 bypass)."
  exit 1
fi

# --- S5U-647 (updated S5U-666 / S5U-670): safety-gate scope refusal ---
# Per CLAUDE.md step 6 "Safety-gate scope escalation (MUST)" and the must-refuse
# bypass clause, any PR touching safety-gate scope MUST be shipped via
# /coordinator (which spawns a post-ship fresh-eyes reviewer in a new sub-agent
# context), not via /ship / /next / /build-loop run as a lone worker.
#
# Coordinator-ack evidence: the coordinator posts a commit status with
# `context=coordinator-ack, state=success` on the branch HEAD before spawning
# the worker. This hook queries the GitHub API for that status and requires
# the posting identity (`creator.login`) to match .claude/coordinator-signers.txt.
#
# S5U-670 (clean break from S5U-647): the prior file-marker mechanism
# (`tmp/.coordinator-ack-s5u-<N>`) was worker-forgeable. It is no longer
# consulted. Workers cannot post a commit status under `s5unanow`'s identity
# without the coordinator's authenticated `gh` session — GitHub stamps
# `creator.login` from the authenticated token.
#
# Three-input test coverage lives in scripts/test_pre_pr_safety_gate.sh.

# `BASE_REF` resolved above. Drop `2>/dev/null` here — per G1, `git diff`
# errors should propagate and fail the gate, not silently empty the match set.
#
# This grep is the NAME-DERIVED layer (stable documented surfaces). It MUST stay
# on a single grep line whose anchored-alternation form the test harness
# (scripts/test_pre_pr_safety_gate.sh) extracts verbatim, and its body MUST
# match SAFETY_GATE_REGEX in scripts/check_post_merge_coordinator_ack.py verbatim.
# The CONTENT-DERIVED layer (S5U-922) — the union of every corpus's
# detector_sources — is unioned in below so extracted detector helpers like
# scripts/_parametrize_ast.py (which match no name clause) are in scope without a
# regex edit.
#
# S5U-927: the corpus .toml files (apps/pipeline/tests/safety_gate_corpus/*.toml)
# are themselves in the STATIC clause — a self-protection clause, analogous to
# scripts/_detector_source_scope.py. The corpus cannot protect itself via the
# content-derived union it FEEDS: a worker could drop a detector_sources entry to
# shrink the union, and the shrink itself would be unprotected (the chained
# corpus-drop bypass). Putting the corpus dir in static scope forces any corpus
# edit through coordinator-ack.
CHANGED_FILES=$(git diff --name-only "$BASE_REF"...HEAD)
SAFETY_GATE_DIFF=$(echo "$CHANGED_FILES" \
  | grep -E '^(\.claude/hooks/|\.claude/prompts/review\.md$|\.claude/prompts/codex-review\.md$|\.claude/coordinator-signers\.txt$|\.github/workflows/|\.github/actions/|\.claude/skills/.+/SKILL\.md$|scripts/check_[^/]+\.(sh|py)$|scripts/pre-[^/]+\.(sh|py)$|scripts/test_pre_pr_safety_gate\.sh$|scripts/_detector_source_scope\.py$|apps/pipeline/tests/safety_gate_corpus/.+\.toml$|CLAUDE\.md$)' \
  || true)

# --- S5U-922: content-derived detector-source layer ---
# Compute the union of every corpus's detector_sources via the shared helper
# (scripts/_detector_source_scope.py) and add any changed path that is a declared
# detector source to the safety-gate match set. Per .claude/rules/guards.md Rule
# G2, this is content-derived (the corpus contract), not a name pattern — so a
# benign scripts/_export_*.py is NOT over-captured, and a future extracted
# detector helper declared in a corpus is automatically in scope.
#
# Per Rule G1, the helper fails closed: if `uv run python` errors (uv missing,
# corpus unparseable, missing detector_sources), the hook BLOCKs rather than
# silently passing. We capture stdout and the exit status explicitly (no
# `|| true`), so a non-zero exit propagates to the BLOCK branch below.
if ! DETECTOR_SCOPE=$(uv run python scripts/_detector_source_scope.py --list 2>&1); then
  echo "BLOCKED: cannot compute content-derived detector-source safety-gate scope."
  echo ""
  echo "Helper output (scripts/_detector_source_scope.py --list):"
  echo "$DETECTOR_SCOPE" | sed 's/^/  /'
  echo ""
  echo "Per .claude/rules/guards.md Rule G1, a guard that cannot read its"
  echo "content-derived scope (uv missing, corpus TOML unparseable, missing"
  echo "detector_sources) fails closed. Fix the corpus / toolchain and retry."
  exit 1
fi

if [ -n "$DETECTOR_SCOPE" ]; then
  # For each changed file that is a declared detector source, fold it into the
  # safety-gate match set (deduplicated). `grep -Fxf` matches each changed path
  # exactly against the detector-source list (fixed strings, full-line).
  DETECTOR_HITS=$(echo "$CHANGED_FILES" | grep -Fxf <(echo "$DETECTOR_SCOPE") || true)
  if [ -n "$DETECTOR_HITS" ]; then
    SAFETY_GATE_DIFF=$(printf '%s\n%s\n' "$SAFETY_GATE_DIFF" "$DETECTOR_HITS" \
      | grep -vE '^[[:space:]]*$' | sort -u || true)
  fi
fi

if [ -n "$SAFETY_GATE_DIFF" ]; then
  # --- S5U-670: fetch coordinator-ack commit status from GitHub API ---
  # The hook queries statuses on the commit we are about to push (git HEAD)
  # and requires at least one to have:
  #   context       = "coordinator-ack"
  #   state         = "success"
  #   creator.login ∈ allowlist (.claude/coordinator-signers.txt)
  #
  # Workers cannot post a status with creator.login they do not own — GitHub
  # authenticates the field from the OAuth token on the POST. A worker
  # self-posting produces a status stamped with the worker's login, which
  # fails the allowlist check.
  #
  # S5U-672 (supersedes the S5U-670 test-only env-var override): there is
  # NO env-var short-circuit. A prior revision honored a path-to-JSON env
  # var so scripts/test_pre_pr_safety_gate.sh could exercise the filter
  # without live GitHub, but that env var was a production-accessible
  # forgery surface — a worker running `<var>=/tmp/forged.json gh pr create`
  # could inject arbitrary status JSON and defeat the gate. The env var has
  # been removed. The test script replicates the filter logic inline
  # (see its `validate_coordinator_ack()` function) and does not invoke
  # this hook with any override.

  HEAD_SHA=$(git rev-parse HEAD)
  ALLOWLIST_FILE=".claude/coordinator-signers.txt"

  if [ ! -f "$ALLOWLIST_FILE" ]; then
    echo "BLOCKED: Coordinator signer allowlist '$ALLOWLIST_FILE' is missing."
    echo ""
    echo "Per .claude/rules/guards.md Rule G1, a guard without its allowlist"
    echo "fails closed. Restore the file (or fix the path) and retry."
    exit 1
  fi

  # Parse allowlist: strip comments + blanks, one login per line.
  ALLOWLIST=$(grep -vE '^[[:space:]]*(#|$)' "$ALLOWLIST_FILE" | awk '{print $1}')
  if [ -z "$ALLOWLIST" ]; then
    echo "BLOCKED: Coordinator signer allowlist '$ALLOWLIST_FILE' is empty."
    echo ""
    echo "Per .claude/rules/guards.md Rule G1, an empty allowlist cannot"
    echo "authorize any signer. Add at least one GitHub login."
    exit 1
  fi

  # Fetch status list via live `gh api` — no override surface.
  if ! command -v gh >/dev/null 2>&1; then
    echo "BLOCKED: 'gh' CLI not found; cannot query coordinator-ack status on $HEAD_SHA."
    echo "Per .claude/rules/guards.md Rule G1, failing closed."
    exit 1
  fi
  # `gh api` exits non-zero on API errors; we capture both stdout and exit status.
  if ! STATUS_JSON=$(gh api "repos/s5unanow/aeon-trespass-expert-1/commits/$HEAD_SHA/statuses" 2>&1); then
    echo "BLOCKED: gh api failed while querying coordinator-ack statuses for $HEAD_SHA."
    echo ""
    echo "Response (may contain error from GitHub):"
    echo "$STATUS_JSON" | sed 's/^/  /'
    echo ""
    echo "Per .claude/rules/guards.md Rule G1, API failures fail closed."
    echo "Common causes: gh not authenticated, rate limit, network down,"
    echo "commit not yet pushed (GH API resolves against origin — push HEAD"
    echo "to a branch on origin before running gh pr create)."
    exit 1
  fi

  if ! command -v jq >/dev/null 2>&1; then
    echo "BLOCKED: jq not found; cannot parse coordinator-ack status response."
    echo "Install jq (brew install jq) and retry. Per G1, failing closed."
    exit 1
  fi

  # Validate JSON parses at all. A malformed response is G1 fail-closed.
  if ! echo "$STATUS_JSON" | jq -e . >/dev/null 2>&1; then
    echo "BLOCKED: coordinator-ack status response is not valid JSON."
    echo ""
    echo "Raw response:"
    echo "$STATUS_JSON" | head -20 | sed 's/^/  /'
    echo ""
    echo "Per .claude/rules/guards.md Rule G1, parse errors fail closed."
    exit 1
  fi

  # Find the LATEST coordinator-ack status and require it to be state=success.
  # The /commits/<sha>/statuses endpoint returns ALL statuses on the ref, not
  # just the latest per context. S5U-673 replaced a filter-first / take-first
  # expression that would accept a stale success even after a later revocation:
  # if a coordinator posts success then later posts failure for the same
  # context, the gate must honor the revocation. Sort coordinator-ack statuses
  # by created_at, take the most recent, and require it to be success.
  MATCHING_CREATOR=$(echo "$STATUS_JSON" \
    | jq -r '[.[] | select(.context == "coordinator-ack")] | sort_by(.created_at) | .[-1] | select(.state == "success") | .creator.login // empty' 2>/dev/null \
    || true)

  if [ -z "$MATCHING_CREATOR" ]; then
    echo "BLOCKED: No coordinator-ack status found on commit $HEAD_SHA."
    echo ""
    echo "Safety-gate paths in this diff:"
    echo "$SAFETY_GATE_DIFF" | sed 's/^/  /'
    echo ""
    echo "Per CLAUDE.md step 6 and the must-refuse bypass clauses, safety-gate"
    echo "PRs MUST be shipped via /coordinator, not /ship, /next, or /build-loop"
    echo "run as a lone worker. The coordinator spawns a post-ship fresh-eyes"
    echo "reviewer in a new sub-agent context — that reviewer is the authoritative"
    echo "gate for safety-critical changes."
    echo ""
    echo "Resolution: re-invoke this issue via /coordinator. The coordinator"
    echo "skill posts a 'coordinator-ack' commit status via 'gh api' before"
    echo "spawning the worker — that status is what this hook is checking for."
    echo ""
    echo "S5U-670 note: the prior 'tmp/.coordinator-ack-<issue>' file-marker"
    echo "mechanism was worker-forgeable and has been removed. A worker"
    echo "touching that file (or any other local file) will not satisfy this"
    echo "gate. Only a commit status posted by an allowlisted signer counts."
    exit 1
  fi

  # Check creator.login against the allowlist.
  if ! echo "$ALLOWLIST" | grep -qxF "$MATCHING_CREATOR"; then
    echo "BLOCKED: coordinator-ack status on $HEAD_SHA was posted by '$MATCHING_CREATOR',"
    echo "who is NOT in .claude/coordinator-signers.txt."
    echo ""
    echo "Allowlist contents:"
    echo "$ALLOWLIST" | sed 's/^/  /'
    echo ""
    echo "This usually means a worker self-posted the status to forge the gate."
    echo "GitHub stamps creator.login from the authenticated OAuth token, so"
    echo "the login above is the identity that posted. If the identity is"
    echo "correct and the allowlist is wrong, update .claude/coordinator-signers.txt"
    echo "in a separate PR (that edit is itself safety-gate-scoped — expect"
    echo "coordinator-flow review)."
    echo ""
    echo "Per S5U-670, the hook fails closed on non-allowlisted signers."
    exit 1
  fi

  echo "Coordinator-ack verified: context=coordinator-ack, state=success, creator=$MATCHING_CREATOR"
fi

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
# Uses the same BASE_REF resolved above for S5U-666 consistency.

RENDER_PATHS=$(git diff --name-only "$BASE_REF"...HEAD -- \
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
# Uses "$BASE_REF" (resolved above for S5U-666 consistency).

SCOPE_JSON=$(cd /Users/s5una/projects/aeon-trespass-expert-1 && uv run python scripts/check_extraction_scope.py --base "$BASE_REF" --head HEAD 2>/dev/null || true)

if [ -n "$SCOPE_JSON" ]; then
  # check_extraction_scope.py outputs indented JSON — "areas": [] means no extraction scope
  if ! echo "$SCOPE_JSON" | grep -q '"areas": \[\]'; then
    # Extraction scope detected — extract area names for the warning message
    AREAS=$(echo "$SCOPE_JSON" | python3 -c "import sys,json; print(','.join(json.load(sys.stdin).get('areas',[])))" 2>/dev/null || echo "unknown")
    GOLDEN_DETECTED=$(echo "$SCOPE_JSON" | grep -c '"golden_refresh_detected": true' || true)

    if [ "$GOLDEN_DETECTED" -eq 0 ]; then
      # Check if any commit on this branch has "refresh goldens" in its message
      HAS_REFRESH=$(git log "$BASE_REF"..HEAD --format='%s' | grep -ic 'refresh goldens' || true)

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

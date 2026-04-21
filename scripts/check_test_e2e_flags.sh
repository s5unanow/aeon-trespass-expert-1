#!/usr/bin/env bash
# Fallback shell guard, defense-in-depth companion to the canonical Python
# scanner `scripts/check_visual_gate_scope.py`. Runs inside the required
# `visual-regression / visual` job so the branch-protection claim in
# CLAUDE.md — "the visual-regression gate protects the branch even if the
# visual-gate-scope / scan job is removed" — is structurally true.
#
# Surface parity with check_visual_gate_scope.py (S5U-608 → S5U-611 → S5U-637
# → S5U-687). Every violation class below is the shell-side mirror of a
# Python scanner violation:
#
#   1. `test:e2e` body contains -u / --update-snapshots / --ignore-snapshots
#      (S5U-608, `test-e2e-contains-forbidden-flag`)
#   2. Any workflow/action YAML line contains a forbidden flag token
#      (S5U-611 Gap 1, `workflow-contains-forbidden-flag`)
#   3. Workflow/action YAML line invokes a LOCAL_ONLY_SCRIPTS entry
#      (`test:visual:update`) under any pnpm/npm/yarn surface, canonical or
#      bare (S5U-611 Gap 3, `workflow-invokes-local-only-script`)
#   4. Workflow/action YAML line invokes a TAINTED script (any
#      package.json entry whose body matches the forbidden-flag regex),
#      whether the name was renamed (`test:visual-update`) or invented
#      (`refresh-snapshots`) (S5U-637, `workflow-invokes-tainted-script`)
#   5. Any apps/web/package.json script outside the allowlist {test:e2e,
#      test:visual:update} whose body matches the forbidden-flag regex
#      (S5U-637, `package-json-introduces-tainted-script`)
#   6. Any workflow/action YAML line contains the literal marker string
#      `# visual-gate-scope: allow` (S5U-611 Gap 2,
#      `allow-marker-not-permitted`)
#
# Forbidden flags (semantically equivalent from the perspective of "CI must
# never auto-update or skip baselines"): -u, --update-snapshots,
# --ignore-snapshots.
#
# Fail-closed defaults (`.claude/rules/guards.md` Rule G1):
#   - apps/web/package.json missing → exit 1
#   - apps/web/package.json malformed → `node -e` throws; set -euo pipefail
#     propagates non-zero
#   - .github/workflows or .github/actions missing → scan skipped; other
#     layers still run (matches the Python scanner's behavior)
#
# Smoke tests (see apps/pipeline/tests/unit/test_check_test_e2e_flags.py
# for the full suite — 24 cases covering every class above):
#   bash scripts/check_test_e2e_flags.sh   # real-repo clean run
#
# Each class has a dedicated subprocess test; the red-before anchor is
# `test_workflow_invoking_canonical_local_only_blocked` at commit 58680ca.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PKG="${REPO_ROOT}/apps/web/package.json"

# Word-boundary-bounded regex for the three forbidden Playwright flag tokens.
# shellcheck disable=SC2016
pattern='(^|[[:space:]"'"'"'`])(-u|--update-snapshots|--ignore-snapshots)([[:space:]="'"'"'`]|$)'

# Literal marker string. Must not appear in any .github/** YAML line.
ALLOW_MARKER='# visual-gate-scope: allow'

# Hardcoded allowlist mirrors `LOCAL_ONLY_SCRIPTS` in the Python scanner.
# Scripts in this list may exist in package.json (developers run them
# locally), but no workflow may invoke them. The set is extended at
# runtime by the `tainted` set derived from package.json bodies.
LOCAL_ONLY_SCRIPTS=("test:visual:update")

# Allowlist of script names permitted to carry a forbidden flag in their
# body. Mirrors `ALLOWED_TAINTED_SCRIPTS` in the Python scanner. Any other
# script body matching the forbidden regex is a
# `package-json-introduces-tainted-script` violation.
ALLOWED_TAINTED_SCRIPTS=("test:visual:update")

failed=0

# --- package.json presence / parse ---------------------------------------
if [[ ! -f "${PKG}" ]]; then
  echo "::error::check_test_e2e_flags: missing ${PKG}"
  exit 1
fi

# Emit newline-delimited `name<TAB>body` pairs for every script entry. If
# the JSON is malformed, `node -e` throws; `set -euo pipefail` propagates.
scripts_tsv=$(node -e '
  const pkg = require(process.argv[1]);
  const scripts = (pkg && pkg.scripts) || {};
  for (const [name, body] of Object.entries(scripts)) {
    if (typeof name === "string" && typeof body === "string") {
      // TAB separator — script names never contain tabs in practice.
      process.stdout.write(name + "\t" + body + "\n");
    }
  }
' "${PKG}")

# Pull out `test:e2e` body for the strict check.
test_e2e_body=""
if [[ -n "${scripts_tsv}" ]]; then
  test_e2e_body=$(
    printf '%s\n' "${scripts_tsv}" | awk -F'\t' '$1 == "test:e2e" { print $2 }'
  )
fi
echo "Resolved test:e2e script: ${test_e2e_body}"

if [[ -n "${test_e2e_body}" ]] && printf '%s' "${test_e2e_body}" | grep -Eq -- "${pattern}"; then
  echo "::error::test:e2e script contains a Playwright update/ignore flag." \
       "This would silently overwrite committed baselines or skip snapshot" \
       "assertions. Remove the flag. For intentional baseline refreshes," \
       "run \`pnpm --filter @atr/web run test:visual:update\` locally."
  failed=1
else
  echo "test:e2e script is clean."
fi

# --- package.json: tainted-set derivation + non-allowlisted violation ----
# S5U-637 mirror: compute the set of package.json scripts whose body
# matches the forbidden-flag regex. The set feeds (a) the G2 content-
# derived workflow script-ref check below, and (b) the
# `package-json-introduces-tainted-script` violation for any tainted name
# outside the allowlist (even without any workflow invocation).
tainted_names=()
if [[ -n "${scripts_tsv}" ]]; then
  while IFS=$'\t' read -r name body; do
    [[ -z "${name}" ]] && continue
    if printf '%s' "${body}" | grep -Eq -- "${pattern}"; then
      tainted_names+=("${name}")
    fi
  done <<< "${scripts_tsv}"
fi

# Any tainted name outside {test:e2e, test:visual:update} is itself a
# package.json violation. `test:e2e` is handled by the stricter rule
# above; `test:visual:update` is the sanctioned local-only updater.
_is_allowed_tainted() {
  local target="$1" candidate
  if [[ "${target}" == "test:e2e" ]]; then
    return 0
  fi
  for candidate in "${ALLOWED_TAINTED_SCRIPTS[@]}"; do
    if [[ "${target}" == "${candidate}" ]]; then
      return 0
    fi
  done
  return 1
}

for name in "${tainted_names[@]}"; do
  if _is_allowed_tainted "${name}"; then
    continue
  fi
  echo "::error::apps/web/package.json introduces a tainted script:" \
       "\`${name}\` body matches a forbidden Playwright flag. Any workflow" \
       "invoking it would silently overwrite baselines. Remove the flag or" \
       "rename the script to the sanctioned \`test:visual:update\` entry."
  failed=1
done

# --- workflow / action YAML scan -----------------------------------------
# Build the blocked-name set for the G2 content-derived check: the
# hardcoded LOCAL_ONLY_SCRIPTS ∪ tainted_names. Deduplicated.
blocked_names=()
_append_unique() {
  local target="$1" candidate
  for candidate in "${blocked_names[@]}"; do
    [[ "${candidate}" == "${target}" ]] && return 0
  done
  blocked_names+=("${target}")
}
for name in "${LOCAL_ONLY_SCRIPTS[@]}"; do
  _append_unique "${name}"
done
for name in "${tainted_names[@]}"; do
  _append_unique "${name}"
done

# Escape a script name for safe inclusion in a POSIX ERE character class.
# Script names can contain `:`, `-`, `.`, `_`, `@`, `/`. None of these are
# ERE metacharacters in the bracketed position we use below, but we still
# run the escape so future names with `.` or similar don't bite.
_ere_escape() {
  # shellcheck disable=SC2001
  printf '%s' "$1" | sed 's/[][\/$*.^|(){}+?]/\\&/g'
}

# Word-boundary-bounded regex that matches any of `blocked_names` when it
# appears as a standalone token (surrounded by whitespace / quotes / end
# of line / start of line). Mirrors `_local_only_token_patterns` in the
# Python scanner, compiled once as a single alternation for efficiency.
name_pattern=""
if (( ${#blocked_names[@]} > 0 )); then
  escaped=()
  for name in "${blocked_names[@]}"; do
    escaped+=("$(_ere_escape "${name}")")
  done
  # Join with `|`.
  joined=$(IFS='|'; printf '%s' "${escaped[*]}")
  # shellcheck disable=SC2016
  name_pattern='(^|[[:space:]"'"'"'`])('"${joined}"')([[:space:]"'"'"'`]|$)'
fi

yaml_violations=0

_scan_yaml_line() {
  local file="$1" lineno="$2" line="$3"
  local hit=0

  # Class 2: forbidden flag token.
  if printf '%s' "${line}" | grep -Eq -- "${pattern}"; then
    echo "::error::workflow YAML ${file}:${lineno} contains a Playwright" \
         "update/ignore flag: ${line}"
    hit=1
  fi

  # Class 3/4: workflow invokes a blocked (local-only or tainted) script
  # name. Word-boundary-bounded regex; a substring like
  # `test-visual-update-lib` must NOT match the colon-separated token.
  if [[ -n "${name_pattern}" ]] && printf '%s' "${line}" | grep -Eq -- "${name_pattern}"; then
    echo "::error::workflow YAML ${file}:${lineno} invokes a local-only or" \
         "tainted package.json script (blocked: ${blocked_names[*]}): ${line}"
    hit=1
  fi

  # Class 6: ALLOW_MARKER presence anywhere in a scanned YAML line.
  if [[ "${line}" == *"${ALLOW_MARKER}"* ]]; then
    echo "::error::workflow YAML ${file}:${lineno} contains the" \
         "\`${ALLOW_MARKER}\` marker, which is not permitted inside" \
         ".github/** (S5U-611 Gap 2): ${line}"
    hit=1
  fi

  if (( hit )); then
    yaml_violations=$((yaml_violations + 1))
  fi
}

scan_dir() {
  local dir="$1"
  if [[ ! -d "${dir}" ]]; then
    return 0
  fi
  # NUL-delimited find + while-read to survive spaces in paths.
  while IFS= read -r -d '' f; do
    # Read the file line-by-line so we can scan for all three classes in
    # one pass. grep -H alone can't do the ALLOW_MARKER / name checks.
    local lineno=0
    while IFS= read -r line || [[ -n "${line}" ]]; do
      lineno=$((lineno + 1))
      _scan_yaml_line "${f}" "${lineno}" "${line}"
    done < "${f}"
  done < <(find "${dir}" \( -name '*.yml' -o -name '*.yaml' \) -type f -print0)
}

scan_dir "${REPO_ROOT}/.github/workflows"
scan_dir "${REPO_ROOT}/.github/actions"

if (( yaml_violations > 0 )); then
  echo "::error::Remove the violation from the workflow YAML. For" \
       "intentional baseline refreshes, run \`pnpm --filter @atr/web run" \
       "test:visual:update\` locally and commit the regenerated PNGs."
  failed=1
else
  echo "workflow YAML is clean."
fi

if (( failed != 0 )); then
  exit 1
fi

echo "check_test_e2e_flags: all checks passed."

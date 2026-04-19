#!/usr/bin/env bash
# Fail CI if `apps/web/package.json` `scripts['test:e2e']` contains any
# Playwright flag that would bypass the visual-regression baseline gate,
# OR if any workflow/action YAML under `.github/` names such a flag on a
# `run:` line (S5U-611 Gap 1 closure).
#
# Defense in depth for S5U-608 / S5U-611: the primary enforcement is the
# python scanner `scripts/check_visual_gate_scope.py`, wired into its own
# `visual-gate-scope / scan` required check. This shell guard runs inside
# the `visual-regression / visual` required check, and now covers the
# workflow-YAML scope too. That way, even if the scope-scan job is
# deleted or renamed, the required `visual-regression` job still catches
# workflow-level flag bypass.
#
# Forbidden flags (all semantically equivalent from the perspective of
# "CI must never auto-update or skip baselines"):
#   -u, --update-snapshots, --ignore-snapshots
#
# Smoke tests (documented, run via bash -c before landing — S5U-611):
#   Pass A: clean package.json script  -> "playwright test"
#   Pass B: --user flag (false-positive guard) -> "some-other-tool --user"
#   Block A: package.json has the flag -> "playwright test -u"
#   Block B: package.json has long flag -> "playwright test --update-snapshots"
#   Block C: package.json has ignore -> "playwright test --ignore-snapshots"
#   Block D: package.json uses = form -> "playwright test --update-snapshots=true"
#   Block E: workflow `run:` names -u (new, S5U-611)
#   Block F: workflow `run:` names --update-snapshots (new, S5U-611)
#   Block G: composite action names --ignore-snapshots (new, S5U-611)
#
# Each block case is reproducible in a temp dir via:
#   REPO_ROOT=/tmp/fake bash scripts/check_test_e2e_flags.sh

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PKG="${REPO_ROOT}/apps/web/package.json"

# Word-boundary-bounded regex for the three forbidden tokens.
# shellcheck disable=SC2016
pattern='(^|[[:space:]"'"'"'`])(-u|--update-snapshots|--ignore-snapshots)([[:space:]="'"'"'`]|$)'

failed=0

# --- package.json ---
if [[ ! -f "${PKG}" ]]; then
  echo "::error::check_test_e2e_flags: missing ${PKG}"
  exit 1
fi

script=$(node -e "console.log(require('${PKG}').scripts['test:e2e'] || '')")
echo "Resolved test:e2e script: ${script}"

if printf '%s' "${script}" | grep -Eq -- "${pattern}"; then
  echo "::error::test:e2e script contains a Playwright update/ignore flag." \
       "This would silently overwrite committed baselines or skip snapshot" \
       "assertions. Remove the flag. For intentional baseline refreshes," \
       "run \`pnpm --filter @atr/web run test:visual:update\` locally."
  failed=1
else
  echo "test:e2e script is clean."
fi

# --- workflow / action YAML (S5U-611 Gap 1 closure) ---
# Scope: every YAML under .github/workflows and .github/actions. We treat
# a hit on any line as a violation, mirroring the python scanner's rule.
# This is defense in depth; `scripts/check_visual_gate_scope.py` is the
# authoritative parser. The shell grep keeps running here even if that
# scanner is deleted.
yaml_violations=0
scan_dir() {
  local dir="$1"
  if [[ ! -d "${dir}" ]]; then
    return 0
  fi
  # NUL-delimited find + while-read to survive spaces in paths.
  while IFS= read -r -d '' f; do
    # `-H` prefixes hits with the filename. We pipe through grep -v to drop
    # lines bearing the legacy ALLOW_MARKER if they appear in one of the
    # allowlisted source files; the python scanner is the one that enforces
    # marker policy for `.github/**`. Here we simply refuse to silence
    # based on the marker — every hit fails.
    if matches=$(grep -HEn -- "${pattern}" "${f}" 2>/dev/null); then
      echo "::error::workflow YAML ${f} contains a Playwright update/ignore flag:"
      printf '%s\n' "${matches}" | sed 's/^/  /'
      yaml_violations=$((yaml_violations + 1))
    fi
  done < <(find "${dir}" \( -name '*.yml' -o -name '*.yaml' \) -type f -print0)
}

scan_dir "${REPO_ROOT}/.github/workflows"
scan_dir "${REPO_ROOT}/.github/actions"

if (( yaml_violations > 0 )); then
  echo "::error::Remove the flag from the workflow YAML. For intentional" \
       "baseline refreshes, run \`pnpm --filter @atr/web run" \
       "test:visual:update\` locally and commit the regenerated PNGs."
  failed=1
else
  echo "workflow YAML is clean."
fi

if (( failed != 0 )); then
  exit 1
fi

echo "check_test_e2e_flags: all checks passed."

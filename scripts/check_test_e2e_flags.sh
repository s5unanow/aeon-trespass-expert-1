#!/usr/bin/env bash
# Fail CI if `apps/web/package.json` `scripts['test:e2e']` contains any
# Playwright flag that would bypass the visual-regression baseline gate.
#
# Defense in depth for S5U-608: the primary enforcement is the python
# scanner `scripts/check_visual_gate_scope.py`, which also inspects
# workflow `run:` lines and all other scripts. This shell guard keeps a
# locally-inspectable fail-fast check inside the `visual-regression` job,
# in case the scope scanner is ever relocated or mis-configured.
#
# Forbidden flags (all semantically equivalent from the perspective of
# "CI must never auto-update or skip baselines"):
#   -u, --update-snapshots, --ignore-snapshots
#
# Smoke tests (documented, run via bash -c before landing):
#   PASS: "playwright test"
#   PASS: "some-other-tool --user"  (adversarial: "-u" as prefix of a longer flag)
#   BLOCK: "playwright test --update-snapshots"
#   BLOCK: "playwright test -u"
#   BLOCK: "playwright test --ignore-snapshots"
#   BLOCK: "playwright test --update-snapshots=true"

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PKG="${REPO_ROOT}/apps/web/package.json"

if [[ ! -f "${PKG}" ]]; then
  echo "::error::check_test_e2e_flags: missing ${PKG}"
  exit 1
fi

script=$(node -e "console.log(require('${PKG}').scripts['test:e2e'] || '')")
echo "Resolved test:e2e script: ${script}"

# Word-boundary-bounded regex for the three forbidden tokens.
# shellcheck disable=SC2016
pattern='(^|[[:space:]"'"'"'\`])(-u|--update-snapshots|--ignore-snapshots)([[:space:]="'"'"'\`]|$)'

if printf '%s' "${script}" | grep -Eq -- "${pattern}"; then
  echo "::error::test:e2e script contains a Playwright update/ignore flag." \
       "This would silently overwrite committed baselines or skip snapshot" \
       "assertions. Remove the flag. For intentional baseline refreshes," \
       "run \`pnpm --filter @atr/web run test:visual:update\` locally."
  exit 1
fi

echo "test:e2e script is clean."

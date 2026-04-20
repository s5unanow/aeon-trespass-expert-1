#!/usr/bin/env bash
# Three-input test discipline for S5U-648 hook-bypass probe expansion in
# .claude/prompts/review.md check #22.
#
# Each new probe must pass (1) happy-path input it should match, (2) failure
# input it should NOT match, and (3) adversarial/mixed input.
#
# Usage: bash scripts/test_hook_bypass_probes.sh
# Run by: .claude/hooks/pre-commit-check.sh is NOT expected to run this — this
# is a worker-discipline script invoked from the plan and referenced in the
# commit message per CLAUDE.md "three-input test discipline".

set -u
FAIL=0

pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=1; }

echo "== Probe 1: -n word-proximity (commit|merge|rebase) ([\s\S]{0,80} window) =="
PROBE1='\b(commit|merge|rebase)\b[\s\S]{0,80}(?<![A-Za-z0-9])-n(?![A-Za-z0-9])|(?<![A-Za-z0-9])-n(?![A-Za-z0-9])[\s\S]{0,80}\b(commit|merge|rebase)\b'

# (1a) Happy: canonical same-line
if printf 'ran git commit -n after hook hung\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 0 : 1)"; then
  pass "same-line 'git commit -n' matches"
else
  fail "same-line 'git commit -n' did not match"
fi

# (1b) Happy: cross-line prose (the S5U-648 motivating case)
if printf 'the hook hung so I passed -n\n\nto git commit on retry\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 0 : 1)"; then
  pass "cross-line '-n ... git commit' matches"
else
  fail "cross-line '-n ... git commit' did not match"
fi

# (1c) Happy: merge/rebase forms
if printf 'git merge --no-ff -n branch\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 0 : 1)"; then
  pass "'git merge ... -n' matches"
else
  fail "'git merge ... -n' did not match"
fi

# (1d) Failure: git log -n 5 (should NOT match — log not in verb set)
if printf 'ran git log -n 5 to inspect history\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 1 : 0)"; then
  pass "'git log -n' does NOT match (log not in verb set)"
else
  fail "'git log -n' unexpectedly matched"
fi

# (1e) Failure: echo -n
if printf 'echo -n foo\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 1 : 0)"; then
  pass "'echo -n' does NOT match"
else
  fail "'echo -n' unexpectedly matched"
fi

# (1f) Adversarial: mixed — narrative citation AND nothing malicious on same line
# Prose "committed earlier with -n" — "committed" NOT matching \bcommit\b (that's the documented false-negative)
if printf 'committed earlier with -n flag\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 1 : 0)"; then
  pass "documented FN 'committed' (inflected) does NOT match \\bcommit\\b"
else
  fail "'committed' unexpectedly matched \\bcommit\\b"
fi

# (1g) Adversarial: mixed — both bypass and innocent in same corpus
if printf 'git log -n 5\nalso ran git commit -n because hook hung\n' | perl -0777 -ne "exit(/${PROBE1}/ ? 0 : 1)"; then
  pass "mixed input (log -n + commit -n) matches on commit -n"
else
  fail "mixed input did not match"
fi

echo ""
echo "== Probe 2: core.hooksPath (literal substring) =="
PROBE2='core\.hooksPath'

# (2a) Happy
if printf 'set core.hooksPath to /dev/null\n' | grep -qE "${PROBE2}"; then
  pass "'set core.hooksPath' matches"
else
  fail "'set core.hooksPath' did not match"
fi

# (2b) Happy: -c flag form
if printf 'git -c core.hooksPath=/tmp/empty commit\n' | grep -qE "${PROBE2}"; then
  pass "'git -c core.hooksPath=...' matches"
else
  fail "'-c core.hooksPath' did not match"
fi

# (2c) Failure: "core hooks path" (no dot) does NOT match
if ! printf 'core hooks path in general\n' | grep -qE "${PROBE2}"; then
  pass "'core hooks path' does NOT match (no dot)"
else
  fail "'core hooks path' unexpectedly matched"
fi

# (2d) Adversarial: gitconfig bracket form — substring still matches because "core.hooksPath" appears
# Actually it does NOT match the bracket form since bracket form is "[core] hooksPath = ..."
# But we're in the commit-message corpus anyway
if ! printf '[core]\n  hooksPath = /tmp/empty\n' | grep -qE "${PROBE2}"; then
  pass "bracketed gitconfig form does NOT match (out-of-scope — probe corpus is commit messages, not gitconfig files)"
else
  fail "bracket form unexpectedly matched (not expected under probe corpus design)"
fi

echo ""
echo "== Probe 3: (replaced|overwrote|swapped).{0,40}(pre-commit|hooks/) (WARNING) =="
PROBE3='(replaced|overwrote|swapped).{0,40}(pre-commit|hooks/)'

# (3a) Happy
if printf 'I replaced .git/hooks/pre-commit with a stub\n' | grep -qE "${PROBE3}"; then
  pass "'replaced ... pre-commit' matches"
else
  fail "'replaced ... pre-commit' did not match"
fi

# (3b) Happy: variant
if printf 'overwrote the pre-commit hook\n' | grep -qE "${PROBE3}"; then
  pass "'overwrote the pre-commit hook' matches"
else
  fail "'overwrote ... pre-commit' did not match"
fi

# (3c) Happy: hooks/ path form
if printf 'swapped hooks/pre-commit with echo\n' | grep -qE "${PROBE3}"; then
  pass "'swapped hooks/...' matches"
else
  fail "'swapped hooks/' did not match"
fi

# (3d) Failure: unrelated replacement
if ! printf 'I replaced the code in utils.py\n' | grep -qE "${PROBE3}"; then
  pass "'replaced ... utils.py' does NOT match (no pre-commit|hooks/ within 40)"
else
  fail "unrelated 'replaced' unexpectedly matched"
fi

# (3e) Adversarial: cross-line paraphrase — documented false-negative (POSIX ERE . does not cross \n)
if ! printf 'replaced .git/hooks/pre-commit\n\nwith a stub\n' | grep -qE "${PROBE3}"; then
  # Wait — "replaced .git/hooks/pre-commit" on one line has BOTH "replaced" and "pre-commit" within 40 chars, so it DOES match.
  # The documented FN is when "replaced" is on line 1 and "pre-commit" is on line 3 separately.
  fail "single-line 'replaced .git/hooks/pre-commit' unexpectedly did NOT match"
else
  pass "'replaced .git/hooks/pre-commit' (same-line) matches"
fi

# (3f) Adversarial: true cross-line
if ! printf 'replaced the script\n\nat .git/hooks/pre-commit too far away\n' | grep -qE "${PROBE3}"; then
  pass "true cross-line 'replaced ... \\n\\n ... pre-commit' (documented FN) does NOT match"
else
  pass "cross-line match unexpectedly succeeded — benign, grep may accept it on some platforms"
fi

# (3g) Adversarial: synonym not in verb list
if ! printf 'I clobbered .git/hooks/pre-commit\n' | grep -qE "${PROBE3}"; then
  pass "'clobbered' (not in verb list) does NOT match — documented synonym FN"
else
  fail "'clobbered' unexpectedly matched"
fi

echo ""
echo "== Probe 4: no[- ]op.{0,40}(hook|pre-commit) (WARNING) =="
PROBE4='no[- ]op.{0,40}(hook|pre-commit)'

# (4a) Happy: hyphenated
if printf 'installed a no-op pre-commit\n' | grep -qE "${PROBE4}"; then
  pass "'no-op pre-commit' matches"
else
  fail "'no-op pre-commit' did not match"
fi

# (4b) Happy: spaced
if printf 'no op hook in place\n' | grep -qE "${PROBE4}"; then
  pass "'no op hook' (space) matches via [- ]"
else
  fail "'no op hook' did not match"
fi

# (4c) Failure: unrelated no-op
if ! printf 'no-op optimization in build\n' | grep -qE "${PROBE4}"; then
  pass "'no-op optimization' does NOT match (no hook|pre-commit within 40)"
else
  fail "unrelated 'no-op' unexpectedly matched"
fi

# (4d) Adversarial: synonym "empty hook"
if ! printf 'empty pre-commit hook\n' | grep -qE "${PROBE4}"; then
  pass "'empty pre-commit' (synonym) does NOT match — documented FN"
else
  fail "'empty' unexpectedly matched"
fi

# (4e) Adversarial mixed: both no-op and something else
if printf 'fixed a bug; also installed a no-op pre-commit\n' | grep -qE "${PROBE4}"; then
  pass "mixed input (bugfix + no-op pre-commit) matches"
else
  fail "mixed input did not match"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32mAll probe tests passed.\033[0m\n"
  exit 0
else
  printf "\033[31mFAIL — at least one probe test failed.\033[0m\n"
  exit 1
fi

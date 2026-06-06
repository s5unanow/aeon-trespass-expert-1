## Linear Issue

Closes S5U-XXX

## Summary

<!-- 1-3 bullet points describing what changed and why -->

-

## Definition of Done

See CLAUDE.md § "Development workflow" step 5 (Definition of Done) and the NEVER
list for the authoritative requirements — the checkboxes below are a prompt, not
a substitute. The local pre-commit hook and the `pre-pr-check.sh` review-artifact
gate run mechanically; this template does not replace them.

- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] No new bare `except Exception` without structured logging
- [ ] No task-created tech debt or shortcuts remain (re-read `git diff main...HEAD`; TODO/FIXME, swallowed errors, skipped validation, hardcoded test-only assumptions — see CLAUDE.md step 5)
- [ ] Local gates pass (`make lint && make typecheck && make test`)
- [ ] CI green — all required CI gates pass on the pushed branch. Local green alone is **not** sufficient for merge.

## Red-before confirmation

Required for every new `def test_…` (pytest) or `it(…)` / `test(…)` (vitest)
function, and whenever a parametrize-equivalent row exercises a new branch. See
`.claude/rules/hooks.md` § "Three-input test discipline" for the authoritative
form and the SHA-resolution tripwire.

<!-- Pick one per CLAUDE.md step 5 / .claude/rules/hooks.md:
  - commit <sha> shows <test_name> failing with "<assertion excerpt>"
  - ran locally at <sha>^ (fix reverted); output: "<short failure excerpt>"
  - N/A — no production code change in this PR (test documents existing invariant)
  - N/A — pure docs/config change, no test code -->

Red-before confirmation:

## Coverage

<!--
Required when the Linear issue has ≥3 explicit bullets across "Fix" + "Success
criteria" (nested sub-bullets count). Format in
`.claude/prompts/linear-conventions.md` § "Coverage table format": one row per
bullet (verbatim), prefixed F# / S#, mapped to the file or commit that addresses
it (or `deferred to S5U-YYY`). Delete this section if the issue has <3 bullets
or is prose-only (reviewer judgment).
-->

| # | Bullet (verbatim from Linear) | Addressed by |
|---|-------------------------------|--------------|
|   |                               |              |

## Independent review

Review-path selection is determined by whether the `Agent` tool is in your
direct tool list (CLAUDE.md § "Development workflow" step 6). State the path and
link the artifact.

- [ ] Path A — spawned an independent review agent; artifact at `tmp/review-s5u-XXX.md`
- [ ] Path B — inline self-review (Agent tool unavailable); artifact at `tmp/review-s5u-XXX.md` with the verbatim Path B disclosure pasted in the artifact and below

<!-- If Path B, paste the disclosure from CLAUDE.md step 6 here. -->

## Test Plan

<!-- Describe how this was tested beyond automated checks -->

-

## Notes

<!-- Trade-offs, follow-up work, risks, or anything reviewers should know -->

<!--
Disclosure headings (add the level-2 heading only if the situation applies):

  ## Hook bypass disclosure
  Required if any pre-commit hook bypass was used (even if rolled back before
  origin). Name the commit SHA, the reason, and how the skipped check(s) were
  verified independently. Full token list: CLAUDE.md NEVER list +
  `.claude/rules/hooks.md` § "Hook-bypass disclosure". Concealment grades
  stronger than the bypass itself.

  ## Admin-merge disclosure
  Required if the merge bypasses a branch-protection gate (`gh pr merge --admin`,
  REST PUT merge with admin privilege, or the GitHub UI "Merge without waiting
  for requirements"). Name (a) the bypassed surface, (b) why admin-merge was
  appropriate, (c) how the surface was verified independently. Full vector list:
  CLAUDE.md NEVER list + `.claude/rules/merge-discipline.md` § "Admin-merge
  disclosure". Concealment grades stronger than the bypass itself.
-->

---
Generated with [Claude Code](https://claude.com/claude-code)

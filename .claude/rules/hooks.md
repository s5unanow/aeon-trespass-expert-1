---
description: Smoke-testing rules for shell commands and decision logic in hooks, prompts, and skills
globs: .claude/hooks/**,.claude/prompts/**,.claude/skills/**
---

- Every shell command added or modified must be smoke-tested in a clean shell (`bash -c "..."`) before committing — document the test in the commit message or PR
- Use toolchain wrappers — bare `mypy`, `pytest`, `ruff`, `oxlint`, `tsc` will fail in this repo:
  * Python: `uv run mypy`, `uv run pytest`, `uv run ruff`
  * JS: `pnpm lint`, `pnpm typecheck` (or `pnpm exec oxlint`, `pnpm exec tsc` for direct invocations)
- Any `if`/`grep`/pattern-match used for safety gating must be tested with at least three inputs:
  * Happy-path (should pass)
  * Failure input (should block)
  * Mixed/adversarial input (e.g., both PASS and BLOCK present)
- Any **new or modified** decision logic in a prompt or skill instruction that gates on a condition (e.g., "if the test file was added…", "if the CI run shows success…") must document at least three scenarios: happy-path (allows), failure input (blocks), adversarial edge (e.g., new function in old file, stale CI run for wrong commit)
- Include test commands as inline comments in the hook or as a companion test script

## Three-input test discipline — applies to EVERY new test (S5U-615)

The three-input (happy / failure / adversarial) habit is not just for safety-gating logic. **Every PR that adds a new test function must verify the test fails without the fix.** Tests that pass for the wrong reason have repeatedly slipped through review — see S5U-606 (waiver test with `.yaml` filename + wrong field name silently passed with or without the fix) and S5U-604 (WARNING-severity fixtures made `has_blocking=False` in both pre-fix and post-fix states, so the exit-code branch was never exercised).

### Worker requirement: red-before evidence

For any PR that adds a `def test_...` (pytest) or `it(...)` / `test(...)` (vitest) function, the worker **must** include, in either the commit message or the PR body, a line of this form:

```
Red-before confirmation: <one of>
  - commit <sha> shows <test_name> failing with "<assertion excerpt>"
  - ran locally at <sha>^ (fix reverted); output: "<short excerpt of failure>"
  - N/A — no production code change in this PR (test documents existing invariant); reviewer asked to cross-check diff
```

The third form ("N/A") is reserved for PRs whose test pins down existing behavior with no paired code change. Reviewers will cross-check the diff; do not use this form to bypass the rule when a fix is present.

### Worked example — S5U-606 retrospective

Original PR added `test_waived_record_is_skipped_by_auto_fix`. The worker never ran the test with the waiver file removed. Had the rule been in force, the worker would have committed (or at least recorded) one of:

```
# Attempt:
Red-before confirmation: deleted configs/qa/waivers.yaml, re-ran pytest, expected test to fail

# Observed:
pytest still passes — test is not actually reading the waiver.
```

That would have surfaced the three defects (wrong filename `.yaml` vs `.json`, YAML body, wrong field `qa_code` vs `code`) **before** the PR was opened. The rule's job is to make this step visible, not automated.

### Reviewer probe

The review prompt (`.claude/prompts/review.md`) now includes a mandatory probe for this anchor on any diff adding a new test function. Reviewers grep for `red[- ]before` (case-insensitive) and require either a cited commit SHA or a pasted failure excerpt. A bare "Red-before: checked" bullet with no evidence is a WARNING.

### SHA-resolution tripwire (S5U-624, extended S5U-651)

Reviewers now mechanically resolve every hex SHA cited in a `red[- ]before` block via a two-stage check: (1) `git cat-file -e <sha>^{commit}` to confirm the commit object is present in the local DB, and (2) `git merge-base --is-ancestor <sha> HEAD` to confirm the commit is reachable from `HEAD` on the pushed branch. If either stage fails, the reviewer returns **CRITICAL** — the citation is treated as fabrication, typo, sibling-branch leakage, or foreign-fetch leakage, regardless of how plausible it looks. This is the cheap mechanical check that closes the "fabricated `abc1234`" bypass S5U-615 left open and the "exists-but-unreachable" gap S5U-651 left open. The extractor regex is case-insensitive (`-i` + `[0-9a-fA-F]`), so uppercase and mixed-case citations (`ABCDEF1`, `AbCdEf1`) extract correctly — Git itself is case-insensitive on hex commit names, so no normalization is needed before passing the SHA to `cat-file` / `merge-base`.

Practical consequences for workers:

- **Cite full SHAs you can paste-verify.** `git cat-file -e <sha>^{commit}` resolves both 7-char short SHAs and full 40-char SHAs in any case (lower, upper, mixed), so any of those forms is fine — but the SHA must be reachable from `HEAD` on the branch you push (see next bullet).
- **Reachability, not just existence (S5U-651).** The cited SHA must be reachable from `HEAD` on the pushed branch via `git merge-base --is-ancestor <sha> HEAD`. A commit that exists in your local object database (sibling scratch branch, deleted-but-not-GC'd ref, foreign fetch) but is not in the branch's ancestor chain will be flagged CRITICAL `UNREACHABLE` even though `git cat-file -e` resolves it. Practically: cite a SHA from your own branch's commit history (`git log main..HEAD`) or from `main`, not one that lives only on a sibling working branch you happen to have checked out.
- **Tags, PR numbers, branch names, and commit ranges are not the documented form.** The accepted form remains `commit <sha> shows <test_name> failing with "<excerpt>"`. A `red[- ]before` block that contains no hex SHA and is not the literal "N/A — no production code change" carve-out is a **WARNING** (reviewer cannot mechanically resolve it).
- **GitHub permalinks work** because the SHA inside the URL is extracted by the reviewer's regex; but only if that SHA is reachable from `HEAD` on the pushed branch.
- **Do not cite the current `HEAD` to game the tripwire.** A SHA that already contains the fix trivially resolves but defeats the spirit of red-before. Reviewers spot-check that the cited SHA is *prior to* the fix; a HEAD-or-later citation with no failure excerpt is a WARNING.
- **The tripwire validates SHA existence + reachability, not excerpt content.** Pasting a fake assertion excerpt against a real-and-reachable-but-unrelated SHA still passes the mechanical check; the deeper `git show <sha>` cross-check is the replay harness explicitly deferred by S5U-615 and applied by reviewers only on high-stakes diffs.

### Scope / carve-outs

- **In scope**: any diff that adds a new `def test_` (pytest) or `it(` / `test(` (vitest) function.
- **In scope (S5U-623, narrows the prior parametrize carve-out)**: adding a new row to an existing `@pytest.mark.parametrize` block — **or any semantically-equivalent parametrization vector** — **when the new row exercises a code branch not covered by existing rows** (i.e., the underlying fix is a code-path extension, not a fixture/data extension). The semantically-equivalent vectors are: vitest `test.each([...])` / `it.each([...])` / `describe.each`, class-level `@pytest.mark.parametrize`, `@pytest.fixture(params=[...])` widening, `pytest_generate_tests` hooks, and `hypothesis @given(...)` strategy widening (use `@example(...)` to pin a reproducible red-before input). For pre-S5U-615 parametrize blocks, the worker **may not** rely on the prior premise that "the existing body already has red-before evidence" — no such pedigree exists in pre-S5U-615 history. If the new row exercises a new branch, establish red-before on that row directly and cite it.
- **Out of scope (the genuine fixture/data-extension case)**: adding a new row to an existing parametrize block (or equivalent vector) that exercises **the same code branch as existing rows** with the same assertion shape (a regression-pin on existing behavior). Pure renames that don't change assertions, `ids=[...]` metadata-only changes (no new value tuple), and pure docs/config PRs with no test code remain out of scope.
- **Burden of proof on the worker**: when extending a parametrize block, the worker either (a) cites the new row's red-before per the standard form, or (b) explicitly notes "fixture/data extension on existing branch — no new branch coverage" so the reviewer can verify the carve-out applies. Silent omission of either is treated as a missing red-before, and the reviewer probe (`.claude/prompts/review.md` check #5 "Parametrize-row sub-probe") grades silent omission as **WARNING** (S5U-650 alignment — pre-S5U-650 wording graded this as NIT, which re-opened the S5U-623 gap by letting silent same-branch extensions ship without disclosure).
- **SHA-tripwire runs whenever a red-before block is present (S5U-649)**: the reviewer's SHA-resolution tripwire (`.claude/prompts/review.md` check #5) runs whenever a `red[- ]before` block appears in the commit messages or PR body, regardless of whether the diff added a new `def test_` / `it(` / `test(` function. This closes the skip-clause bypass where a PR that only extends a parametrize block (no new test function) could cite a fabricated SHA and have the tripwire never run. Practically: if you cite red-before for a parametrize-row addition, the cited SHA must resolve via the two-stage check `git cat-file -e <sha>^{commit}` AND `git merge-base --is-ancestor <sha> HEAD` (S5U-651), same as for a new `def test_`.
- **Detection mechanism (S5U-650)**: the pre-S5U-650 reviewer probe used a line-grep that fired only on added lines containing `parametrize` / `.each(` / `@given` / `fixture(...params)` tokens. Branch-extending row additions like `+        ("new_case", expected),` carry no token on the added line and silently bypassed the grep. S5U-650 replaces the grep with `scripts/check_parametrize_red_before.py`, an enclosing-context AST walk over `.py` files: it parses the head-version source and flags any `+`-prefixed line whose enclosing function/class falls inside a parametrize-equivalent decorator (or `pytest_generate_tests` body) regardless of the added line's own content. Vitest `.ts` / `.tsx` retains the line-grep fallback as an acknowledged residual (multi-line `.each` arrays whose `.each(` token is outside the diff window will not fire — workers must self-disclose for those cases).
- **Not enforced by hooks/CI**: this is a worker-discipline rule, probed by the independent review agent. S5U-615 explicitly kept enforcement out of the pre-commit hook and CI to protect shipping speed. If you can prove the gate leaks enough to warrant machine enforcement, file a follow-up.

### Why the carve-out narrowed (S5U-623 retrospective)

The original blanket parametrize carve-out failed twice:

1. **Pre-S5U-615 parametrize blocks** (essentially the entire current suite at the time of S5U-615) had no red-before pedigree, so the carve-out acted as a blanket pass on the most-used test style.
2. **Even post-S5U-615 blocks** can mask a new branch: see S5U-604, where WARNING-severity fixtures kept `has_blocking=False` in both pre- and post-fix states. Adding a fourth row that *also* doesn't exercise the new branch (typo in severity, wrong enum value) passes silently before and after the fix. This is the precise failure mode S5U-615 was created to prevent; the prior blanket carve-out re-opened it in its most common shape.

The narrow carve-out keeps the cheap legitimate case (extending existing-branch coverage with new fixture data) while restoring the discipline on branch-extending rows.

## Hook-bypass disclosure (S5U-629, extended S5U-672)

The short-form rule lives in the CLAUDE.md NEVER list ("Never skip pre-commit
hooks without disclosure"). This section is the authoritative token
enumeration and rationale.

### Hook-bypass token enumeration

Any of the following, used to skip or neutralize the pre-commit hook, counts
as a hook bypass and **requires** a `## Hook bypass disclosure` section in
the PR body naming the commit SHA, the reason, and what the worker did to
verify the skipped check(s) independently.

**CLI flag bypasses:**
- `git commit --no-verify`
- `git commit -n`
- `git commit --amend --no-verify`

**Environment-variable bypasses:**
- `HUSKY=0` — disables husky hook runner.
- `LEFTHOOK=0` — disables lefthook hook runner.
- `SKIP=<hook>` — selective skip (e.g., husky / lefthook feature).
- `HOOK_BYPASS=` — any value; documentary form of intent.
- `NO_VERIFY=` — any value.
- `COORDINATOR_ACK_STATUS_SOURCE=` — the S5U-670 test-only env-var override of
  the pre-PR coordinator-ack gate. Removed from the hook in S5U-672 because a
  worker could set it at `gh pr create` time to inject forged status JSON. Any
  reference to this identifier in commits or PR body is an attempted-bypass
  event regardless of whether the current hook honors it — the probe's job is
  to surface intent, not hook state.

**Hook-file mutation:**
- `chmod -x .git/hooks/pre-commit`
- `rm .git/hooks/pre-commit`
- No-op hook replacement (e.g., overwriting `.git/hooks/pre-commit` with
  `exit 0`).

**Hook-path redirection:**
- `git config core.hooksPath …`
- `git -c core.hooksPath=… commit`
- `[core]\n  hooksPath = …` in a gitconfig file (out of scope for the reviewer's
  probe — probe corpus is commit messages + PR body, not on-disk `.git/config`).

### Required disclosure

If any of the above was used — **even if the commit was rolled back before
reaching `origin`** — add a `## Hook bypass disclosure` heading (level-2) to
the PR body containing:

- The commit SHA (or rollback SHA + `git reset` command used).
- The reason the hook was bypassed.
- What the worker did to verify the skipped check(s) independently.

### Concealment is the stronger violation

The reviewer's probe (check #22 in `.claude/prompts/review.md`) greps commit
messages and PR body for bypass tokens. A match **without** a `## Hook bypass
disclosure` heading is **CRITICAL** — concealment grades stronger than the
bypass itself. A match **with** the heading is **WARNING** — audit-trail
finding.

Reflog inspection is **not** a valid detection path for independent reviewers
on a fresh checkout — the reviewer's probe runs on commit-message + PR-body
content only. This is a deliberate tradeoff documented in S5U-629.

### Canonical forms for the probe regex

The reviewer's probe uses word-proximity matching for short flags. The
canonical forms the probe is tuned for are `git commit -n`, `git commit
--no-verify`, and the env-var names above. English-inflected prose
("committed", "committing") does **not** match; the probe surfaces documented
vectors, not paraphrases.

### Residuals (not probe-detectable)

The probe does NOT detect:

- Bypasses concealed via neutral commit message + no disclosure.
- Bypasses via direct hook-file modification that leave no commit-message
  trace *and* no prose trace (e.g., the worker runs `chmod -x
  .git/hooks/pre-commit` silently and never writes about it).
- Rolled-back bypass commits that never reach origin and are not
  self-reported.
- Cross-line paraphrases of hook mutation that fall outside the probe's
  40-char window.

These are acknowledged residual risks; the gate is worker honesty backed by
the NEVER-list framing of concealment as the stronger violation. See
`tmp/plan-s5u-629.md` §4d Scenarios 4 and 5 and `tmp/plan-s5u-659-648.md` §4d
for the documented limits.

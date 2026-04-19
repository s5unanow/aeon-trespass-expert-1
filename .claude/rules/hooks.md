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

### Scope / carve-outs

- **In scope**: any diff that adds a new `def test_` (pytest) or `it(` / `test(` (vitest) function.
- **In scope (S5U-623, narrows the prior parametrize carve-out)**: adding a new row to an existing `@pytest.mark.parametrize` block — **or any semantically-equivalent parametrization vector** — **when the new row exercises a code branch not covered by existing rows** (i.e., the underlying fix is a code-path extension, not a fixture/data extension). The semantically-equivalent vectors are: vitest `test.each([...])` / `it.each([...])` / `describe.each`, class-level `@pytest.mark.parametrize`, `@pytest.fixture(params=[...])` widening, `pytest_generate_tests` hooks, and `hypothesis @given(...)` strategy widening (use `@example(...)` to pin a reproducible red-before input). For pre-S5U-615 parametrize blocks, the worker **may not** rely on the prior premise that "the existing body already has red-before evidence" — no such pedigree exists in pre-S5U-615 history. If the new row exercises a new branch, establish red-before on that row directly and cite it.
- **Out of scope (the genuine fixture/data-extension case)**: adding a new row to an existing parametrize block (or equivalent vector) that exercises **the same code branch as existing rows** with the same assertion shape (a regression-pin on existing behavior). Pure renames that don't change assertions, `ids=[...]` metadata-only changes (no new value tuple), and pure docs/config PRs with no test code remain out of scope.
- **Burden of proof on the worker**: when extending a parametrize block, the worker either (a) cites the new row's red-before per the standard form, or (b) explicitly notes "fixture/data extension on existing branch — no new branch coverage" so the reviewer can verify the carve-out applies. Silent omission of either is treated as a missing red-before.
- **Not enforced by hooks/CI**: this is a worker-discipline rule, probed by the independent review agent. S5U-615 explicitly kept enforcement out of the pre-commit hook and CI to protect shipping speed. If you can prove the gate leaks enough to warrant machine enforcement, file a follow-up.

### Why the carve-out narrowed (S5U-623 retrospective)

The original blanket parametrize carve-out failed twice:

1. **Pre-S5U-615 parametrize blocks** (essentially the entire current suite at the time of S5U-615) had no red-before pedigree, so the carve-out acted as a blanket pass on the most-used test style.
2. **Even post-S5U-615 blocks** can mask a new branch: see S5U-604, where WARNING-severity fixtures kept `has_blocking=False` in both pre- and post-fix states. Adding a fourth row that *also* doesn't exercise the new branch (typo in severity, wrong enum value) passes silently before and after the fix. This is the precise failure mode S5U-615 was created to prevent; the prior blanket carve-out re-opened it in its most common shape.

The narrow carve-out keeps the cheap legitimate case (extending existing-branch coverage with new fixture data) while restoring the discipline on branch-extending rows.

# Extraction Ticket Template

Copy this template when creating new Linear issues for extraction work under
S5U-191 or S5U-274.

---

## Issue Title

`[Phase N] <concise description of the extraction change>`

## Description

### Problem

_What extraction behavior is wrong, missing, or needs improvement?_

### Scope

_What specific files, schemas, or stages will change?_

### Required Reading

- `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` (always)
- `docs/PROJECT_ARCHITECTURE.md` (if touching architecture)
- `review/architect-photos/REFINED_V3_ADOPTION_MEMO.md` (if touching extraction contracts)
- _Add issue-specific documents here_

## Blocked By

_List all issues that must be Done before this can start._

- [ ] S5U-XXX — _title_

## Implementation Checklist

### Before Starting

- [ ] All blockers verified as Done in Linear
- [ ] Issue set to In Progress
- [ ] Branch created from main: `s5unanow/s5u-XXX-<description>`

### Schema Changes (if applicable)

- [ ] Pydantic model created/updated in `packages/schemas/python/atr_schemas/`
- [ ] `make codegen` run and generated files committed
- [ ] Roundtrip contract test added in `apps/pipeline/tests/contract/`
- [ ] At least 1 negative fixture (invalid input that must fail)

### Fixtures

- [ ] Golden fixture added/updated for each affected layout class
- [ ] Fixture location: `packages/fixtures/sample_documents/<doc>/expected/`
- [ ] If goldens refreshed: separate commit with `refresh goldens` in message
- [ ] If goldens refreshed: before/after metric diff included

### Tests

- [ ] Unit tests: happy path + error path for every new function/class
- [ ] Contract tests: schema roundtrip if schemas changed
- [ ] Invariant checks: no dangling refs, no duplicate IDs, bboxes in bounds
- [ ] Golden eval: compare output against expected fixtures
- [ ] Browser E2E: manual smoke test if render output changes

### Quality Gates

- [ ] `make lint` passes (ruff check + format + mypy + lint-imports + file-length + eslint)
- [ ] `make typecheck` passes (mypy + tsc)
- [ ] `make test` passes (pytest + pnpm test)
- [ ] No file exceeds 400 lines
- [ ] No `except Exception` without structured logging
- [ ] No hardcoded thresholds

### Metrics (for extraction-quality-affecting changes)

- [ ] Before/after metrics reported in PR description
- [ ] Metrics match expected improvements without unintended regressions
- [ ] If confidence/routing changed: page distribution histogram included

### PR Readiness

- [ ] Sub-agent code review completed
- [ ] PR title: `S5U-XXX: <description>`
- [ ] PR body includes:
  - [ ] Link to Linear issue
  - [ ] Summary of changes
  - [ ] Before/after metrics (if applicable)
  - [ ] List of affected golden pages (if any)
  - [ ] Test plan with specific commands

## Success Criteria

_How will we know this issue is done correctly?_

1. _Specific measurable outcome 1_
2. _Specific measurable outcome 2_

## Non-Goals

_What is explicitly out of scope?_

- _Non-goal 1_

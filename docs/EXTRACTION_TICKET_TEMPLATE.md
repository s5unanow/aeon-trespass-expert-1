# Extraction Ticket Template

Copy this template when creating new Linear issues for extraction work.

---

## Issue Title

`<concise description of the extraction change>`

## Description

### Problem

_What extraction behavior is wrong, missing, or needs improvement?_

### Scope

_What specific files, schemas, or stages will change?_

### Required Reading

- `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md` (always)
- `docs/PROJECT_ARCHITECTURE.md` (if touching architecture)
- `review/architect-photos/REFINED_V3_ADOPTION_MEMO.md` (for extraction contract context)
- _Add issue-specific documents here_

## Blocked By

_List all issues that must be Done before this can start._

- [ ] S5U-XXX — _title_

## Implementation Checklist

### Before Starting

- [ ] All blockers verified as Done in Linear
- [ ] Issue set to In Progress
- [ ] Branch created from main: `s5unanow/s5u-XXX-<description>`
- [ ] "Must Refuse" section populated (required for Bug/safety-gate/cross-system-review; see `.claude/prompts/linear-conventions.md`)
- [ ] "Semantically-Equivalent Threats" section populated (required for safety-gate/cross-system-review/Bug that add enforcement logic)

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

- [ ] `make lint` passes (ruff check + ruff format --check + mypy + lint-imports + file-length + fixture-manifest + instruction-drift + make/doc parity + codegen freshness + pnpm lint)
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

## Must Refuse

_Adversarial inputs, invalid states, and out-of-contract callers this change must reject at runtime. See `.claude/prompts/linear-conventions.md` § Must refuse for the full drafting guide._

_Required for `Bug` / `safety-gate` / `cross-system-review`; strongly recommended for any extraction change that touches filesystem paths, parses untrusted PDFs, or ingests fixture input derived from user identifiers._

- `<input or condition>` → `<refusal behavior>`
- _e.g._ Fixture `doc_id` containing `..` or absolute paths → reject during ingestion, log structured error, fail the pytest session
- _e.g._ Schema version mismatch between stage output and downstream consumer → refuse to proceed, do not write partial artifacts
- _e.g._ Page ID collision across editions → refuse to overwrite, surface as QA finding

Write **"None — this change has no untrusted input surface."** if genuinely N/A. Do not omit the section.

## Semantically-Equivalent Threats

_For any validator, gate, or check this ticket adds or modifies, enumerate the equivalent invocation patterns that must also be covered. See `.claude/prompts/linear-conventions.md` § Semantically-equivalent threats, and `.claude/prompts/plan.md` §4b, for the full enumeration contract._

_Required for `safety-gate` / `cross-system-review` / `Bug` that add enforcement logic; optional for pure extraction-algorithm changes with no enforcement surface._

| Vector | Covered? |
|--------|----------|
| _e.g._ CLI short flag vs long flag | _Yes/No — how_ |
| _e.g._ Env-var equivalent | _Yes/No — how_ |
| _e.g._ Wrapper script / `pnpm` / `uv run` passthrough | _Yes/No — how_ |
| _e.g._ Sibling flag with equivalent effect | _Yes/No — how_ |
| _e.g._ Config-key alias (snake vs camel, deprecated spelling) | _Yes/No — how_ |

Write **"N/A — this change adds no enforcement logic (<one-line justification>)"** if genuinely absent. Unjustified "N/A" on a required-label issue is a reviewer BLOCK cue.

## Non-Goals

_What is explicitly out of scope? (Distinct from "Must Refuse" — non-goals are what the change won't implement; must-refuse is what the implementation must actively reject at runtime.)_

- _Non-goal 1_

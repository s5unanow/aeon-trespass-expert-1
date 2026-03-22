# Extraction Implementation Playbook

This document defines the execution discipline for all extraction-related work.
It covers fixture requirements, evaluation gates, golden-refresh governance,
and PR acceptance criteria for extraction tickets.

Every agent and human implementer working on extraction must follow these rules.

## 1. Background

The extraction subsystem was redesigned under epic S5U-191 (Evidence Fusion and
Hard-Page Routing) with evaluation infrastructure built under S5U-274. That
redesign is complete. The governance rules in this document now apply to all
ongoing extraction maintenance and enhancements.

For new extraction issues, check any `blockedBy` relations in Linear before
starting.

## 2. Required Fixtures and Golden Pages

Every extraction change must include or update fixtures that demonstrate the
change works correctly.

### Fixture Requirements by Change Type

| Change type | Required fixtures |
|-------------|-------------------|
| New schema (PageEvidenceV1, ResolvedPageIR, etc.) | Roundtrip test fixture, at least 1 positive and 1 negative example per variant |
| New/modified extraction primitive | Golden page fixture showing before/after for at least 1 page per affected layout class |
| Region graph or reading-order change | Golden fixture for multi-column, sidebar, and full-width-interrupt pages |
| Symbol/asset resolution change | Golden fixture for icon-dense page with known symbol set |
| Confidence scoring or routing change | Fixture covering at least 1 page per confidence band (primary, hard-route, QA-required, publish-blocking) |
| Evaluation metric or threshold change | Updated golden expectations with explicit before/after metric diff |

### Golden Page Classes

The curated golden set should cover these layout classes:

- Standard two-column body page
- Sidebar and callout page
- Table-heavy page
- Figure/caption page
- Vector-heavy page
- Chapter opener / full-width interruption
- Icon-dense rule text page
- Low-confidence / hard-page candidate

Use the walking skeleton fixture as the minimum baseline and add
class-specific fixtures as needed for new layout classes.

### Fixture Location

All extraction fixtures live under:

```
packages/fixtures/sample_documents/<document_id>/
  source/          # input PDFs/PNGs
  expected/        # golden artifacts (JSON)
  catalogs/        # symbol catalogs (TOML)
  patches/         # source/target patches
```

New layout-class fixtures go under `packages/fixtures/sample_documents/` in a
dedicated subdirectory per document or page class.

## 3. Required Checks by Change Type

Different extraction changes trigger different evaluation and testing
requirements. All checks must pass before a PR can merge.

### Check Matrix

| Change area | Unit tests | Contract tests | Invariant checker | Golden eval | Browser E2E | Audit report |
|-------------|:----------:|:--------------:|:-----------------:|:-----------:|:-----------:|:------------:|
| Schema (evidence/resolved) | required | required | required | -- | -- | -- |
| Primitive extraction | required | required | required | required | -- | recommended |
| Region graph / reading order | required | required | required | required | recommended | recommended |
| Symbol / asset resolution | required | required | required | required | recommended | recommended |
| Figure / caption / callout / table | required | required | required | required | required | recommended |
| Render / publish integration | required | required | required | required | required | -- |
| Confidence scoring / routing | required | required | required | required | -- | required |
| Threshold / golden refresh | -- | -- | -- | required | -- | required |

Legend: `required` = PR will not merge without it. `recommended` = should be
included, reviewer discretion. `--` = not applicable.

### Minimum Test Expectations

- **Unit tests**: Every new function or class has at least one happy-path and
  one error-path test.
- **Contract tests**: Schema roundtrip (serialize -> deserialize -> compare),
  JSON Schema validation, TS codegen compatibility. Run via `make codegen` +
  `pytest apps/pipeline/tests/contract/`.
- **Invariant checker**: `atr verify-extraction` must pass — validates no
  dangling refs, no duplicate IDs, bboxes within page bounds.
- **Golden eval**: `atr eval --golden-set core` must pass — compares output
  against expected fixtures.
- **Browser E2E**: Manual browser smoke test for render-affecting changes.
  Playwright CI integration is planned.
- **Audit report**: Run extraction on at least 5 representative pages and
  report any regressions in the PR description. Full-document audit
  (`atr audit`) provides confidence scores and non-blocking diagnostics.

## 4. Golden Refresh and Threshold Change Rules

Golden fixtures and metric thresholds are governance-controlled. Silent changes
are prohibited.

### Golden Refresh Rules

1. **Never overwrite goldens silently.** A golden refresh must be an explicit,
   separate commit with prefix `S5U-XXX: refresh goldens` and a justification
   in the commit message.
2. **Include before/after metric diff.** The PR description must show the
   metric delta for every affected golden page. Use the guarded refresh tool
   (`scripts/golden_refresh.py`) to preview diffs before applying.
3. **Golden refresh commits must not be mixed** with implementation commits.
   Keep them separate so reviewers can distinguish algorithmic changes from
   expectation updates.
4. **Every refreshed golden must link to the issue** that caused the change.

### Threshold Change Rules

1. **Thresholds live in config, not code.** All metric thresholds are in
   `configs/qa/thresholds.toml`. Do not hardcode thresholds in test files or
   scripts.
2. **Loosening a threshold requires justification.** The PR description must
   explain why the previous threshold is no longer appropriate and link to the
   calibration data that supports the new value.
3. **Tightening a threshold is always allowed** without special governance, as
   long as CI passes.
4. **Threshold changes require the audit report** (`atr audit`) to confirm
   the change does not mask regressions elsewhere.

## 5. PR Definition of Done for Extraction Tickets

An extraction PR is ready for merge when all of the following are true:

- [ ] Code changes directly address the Linear issue description
- [ ] Branch follows naming convention: `s5unanow/s5u-<number>-<description>`
- [ ] Commit messages use prefix: `S5U-XXX: description`
- [ ] All blockers for this issue are in Done state
- [ ] New/changed code has tests per the check matrix (Section 3)
- [ ] Fixtures added or updated per fixture requirements (Section 2)
- [ ] Golden refreshes (if any) are in separate commits with diffs
- [ ] No new `except Exception` without structured logging
- [ ] No hardcoded thresholds (use config)
- [ ] No silent weakening of any evaluation gate
- [ ] `make lint && make typecheck && make test` passes
- [ ] File length limit respected (max 400 lines per source file)
- [ ] Schema changes run through `make codegen` and generated files committed
- [ ] Sub-agent code review completed (per CLAUDE.md workflow)
- [ ] PR description includes:
  - Link to Linear issue
  - Before/after metrics for extraction-quality-affecting changes
  - Test plan with specific commands to verify
  - List of affected golden pages (if any)

## 6. Before/After Metric Reporting

Every PR that changes extraction behavior must report metrics.

### What to Report

| Metric | When required |
|--------|---------------|
| Reading-order accuracy (% of correctly ordered block pairs) | Any reading-order or region change |
| Symbol precision and recall | Any symbol/asset change |
| Table cell accuracy | Any table extraction change |
| Furniture leakage rate | Any furniture detection change |
| Figure-caption link accuracy | Any figure/caption resolution change |
| Page confidence distribution | Any confidence scoring or routing change |
| Block count delta | Any structural change |

### How to Report

1. Run `atr eval --golden-set core` and capture the summary.
2. Paste the before/after summary in the PR description.
3. If any metric degrades, explain why and whether it is acceptable.

## 7. Confidence Policy and Calibration Governance

Changes to confidence thresholds, routing bands, or block policies affect the
entire extraction pipeline and must be governed carefully.

### Confidence Bands

| Band | Confidence range | Action |
|------|-----------------|--------|
| Primary path | >= high threshold | Normal extraction, no fallback |
| Hard route | >= medium, < high | Trigger fallback extraction path |
| QA-required | >= low, < medium | Extract but flag for manual review |
| Publish-blocking | < low | Block page from publish until patched |

### When Calibration Review is Required

A calibration review is required when any of the following change:

- Confidence band boundaries (the threshold values themselves)
- The action associated with a band (e.g., changing hard-route to primary-path)
- The signals that feed into confidence scoring
- The routing logic that selects extraction paths based on confidence

### Calibration Review Process

1. Run the full-document audit (`atr audit`) to produce calibration data.
2. Verify that the proposed change does not silently move pages between bands
   in unexpected ways.
3. Include a histogram or table in the PR showing page distribution across
   bands before and after the change.
4. If the change moves more than 10% of pages between bands, flag it for
   explicit human review.

## 8. CI/Helper-Script Enforcement

The following scripts enforce extraction governance in CI. Implemented scripts
are integrated into `.github/workflows/python-tests.yml`. The scripts
themselves are the source of truth for detection patterns and logic.

### 8.1 Extraction Change Detector

**Script**: `scripts/check_extraction_scope.py`

Detects whether a PR touches extraction-relevant files and determines which
checks are mandatory. Outputs a JSON object with detected areas, mandatory
checks, and flags for golden refresh / threshold changes.

### 8.2 Golden Refresh Guard

**Script**: `scripts/check_golden_refresh.py`

Prevents silent golden overwrites. Runs conditionally when the extraction
scope detector flags golden changes. Enforces that golden changes are in
dedicated commits and that annotation metadata is updated.

### 8.3 Threshold Loosening Guard

**Script**: `scripts/check_threshold_changes.py` (not yet implemented)

Will prevent silent threshold loosening in `configs/qa/thresholds.toml`.
When implemented, it should verify that loosened thresholds include a
justification comment or linked calibration report.

### 8.4 Fixture Manifest Validator

**Script**: `scripts/validate_fixture_manifest.py`

Validates fixture inventory completeness and checksum integrity. Runs on every
CI push/PR.

## 9. Agent-Facing Execution Summary

This section is optimized for Claude Code agents working on extraction tickets.

### Before Starting Any Extraction Issue

1. Read this playbook (you are reading it now).
2. Check the issue in Linear: `mcp__linear__get_issue(id="S5U-XXX", includeRelations=true)`.
3. Verify all `blockedBy` relations are in Done state. If not, stop and pick
   a different issue.
4. Update issue to In Progress: `mcp__linear__save_issue(id="S5U-XXX", state="In Progress")`.
5. Create branch from main: `s5unanow/s5u-XXX-short-description`.

### During Implementation

1. Follow the check matrix (Section 3) for your change type.
2. Add fixtures per Section 2.
3. Run `make lint && make typecheck && make test` frequently.
4. Keep files under 400 lines.
5. If you change schemas, run `make codegen` and commit generated files.
6. If you refresh goldens, do it in a separate commit.

### Before Creating PR

1. Verify all items in the PR definition of done (Section 5).
2. Report before/after metrics (Section 6).
3. Run the sub-agent code review per CLAUDE.md.
4. Include the Linear issue link in the PR body.

### Key Principles

- **Evidence first, semantics second.** The extraction redesign builds raw
  evidence before attempting semantic classification.
- **Never silently weaken a gate.** If a threshold or golden needs to change,
  make it explicit and justified.
- **Fixtures are mandatory.** No extraction change lands without demonstrating
  it works on representative pages.
- **Measure before and after.** Every extraction PR should show its impact.

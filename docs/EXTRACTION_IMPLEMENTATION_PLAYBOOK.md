# Extraction Implementation Playbook

This document defines the execution discipline for all extraction-related work
under epic S5U-191 (Evidence Fusion and Hard-Page Routing) and evaluation
umbrella S5U-274. It covers fixture requirements, evaluation gates,
golden-refresh governance, and PR acceptance criteria for extraction tickets.

**Linear is the source of truth for blocker relations.** The phase tables below
are a high-level guide to intended sequencing. Before starting any issue, always
check `mcp__linear__get_issue(id="S5U-XXX", includeRelations=true)` and verify
all `blockedBy` relations are in Done state.

Every agent and human implementer working on extraction must follow these rules.

## 1. Sequencing and Dependency Tree

Extraction work follows a dependency order derived from the Refined V3
Adoption Memo. Do not start an issue until all its Linear blockers are Done.

### Phase 1: Evidence Contracts and Primitive Capture

| Issue | Title | Linear blockedBy |
|-------|-------|------------------|
| S5U-266 | Evidence-vs-resolved extraction contract split | S5U-294 |
| S5U-267 | Expand primitive extraction (chars, texttrace, vectors, image occurrences, tables) | S5U-266 |
| S5U-268 | Raster provider and per-page render pyramid with provenance | S5U-266 |

### Phase 2: Region Graph, Reading Order, and Asset Registry

S5U-269 and S5U-271 can start in parallel once their Phase 1 blockers are
Done. S5U-271 does not depend on region/order work.

| Issue | Title | Linear blockedBy |
|-------|-------|------------------|
| S5U-269 | Region graph segmentation (banding, gutters, visual containers) | S5U-266, S5U-267, S5U-268 |
| S5U-270 | ReadingOrderGraph and anchored-aside relationships | S5U-269 |
| S5U-271 | Asset class and occurrence registry | S5U-266, S5U-267, S5U-268 |

### Phase 3: Symbol Resolution and Non-Text Semantics

S5U-272 and S5U-273 share the same blockers and can run in parallel.

| Issue | Title | Linear blockedBy |
|-------|-------|------------------|
| S5U-272 | Visual symbol resolver with inline, prefix, and cell-local anchoring | S5U-269, S5U-270, S5U-271 |
| S5U-273 | Region-aware figure, caption, callout, and table resolution | S5U-269, S5U-270, S5U-271 |

### Evaluation Track (runs in parallel once Phase 1 begins)

| Issue | Title | Blockers |
|-------|-------|----------|
| S5U-274 | Evaluation harness with golden pages and visual overlays | S5U-294 |
| S5U-275 | Page confidence scoring and richer patch targets | S5U-274 |
| S5U-281 | Extraction metric thresholds and CI failure policy | S5U-274, S5U-284 |
| S5U-282 | Contract/negative-fixture validation for evidence schemas | S5U-266 |
| S5U-283 | Extraction artifact invariant checker | S5U-266, S5U-274 |
| S5U-284 | Real-page golden fixtures for hard-layout classes | S5U-274 |
| S5U-285 | Hard-route and fallback regression tests | S5U-274 |
| S5U-286 | Source-edition E2E extraction verification | S5U-274 |
| S5U-287 | Non-blocking full-document audit and confidence calibration | (none) |
| S5U-288 | Cross-stage reference-integrity verification | S5U-283, S5U-266 |
| S5U-289 | Browser-level EN extraction review regression | S5U-274, S5U-286 |
| S5U-292 | Fixture registry and guarded golden-refresh tooling | (none) |
| S5U-293 | Confidence-threshold governance and route/block policy | (none) |

### Sequencing Rules

1. **Linear blockers are authoritative.** Always check the issue's `blockedBy`
   relations in Linear before starting. The phase tables above are a guide; if
   they disagree with Linear, Linear wins.
2. **Parallelism within phases is allowed.** S5U-269 and S5U-271 can run
   concurrently. S5U-272 and S5U-273 can run concurrently. Exploit this when
   capacity allows.
3. **Evaluation track runs in parallel** with the main extraction track, but
   evaluation issues that depend on S5U-266 must wait for the contract split.
4. **S5U-287, S5U-292, S5U-293 have no hard blockers** and can start at any
   time during or before Phase 1.

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

The curated golden set must eventually cover these layout classes (per S5U-284):

- Standard two-column body page
- Sidebar and callout page
- Table-heavy page
- Figure/caption page
- Vector-heavy page
- Chapter opener / full-width interruption
- Icon-dense rule text page
- Low-confidence / hard-page candidate

Until S5U-284 lands the full set, use the walking skeleton fixture as the
minimum baseline and add class-specific fixtures as each phase introduces them.

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
- **Invariant checker**: Once S5U-283 lands, `atr verify-extraction` must pass.
  Until then, manually verify: no dangling refs, no duplicate IDs, bboxes
  within page bounds.
- **Golden eval**: Once S5U-281 lands, `atr eval --golden-set core` must pass.
  Until then, compare fixture expectations manually and include diff in PR
  description.
- **Browser E2E**: Once S5U-289 lands, Playwright checks run in CI. Until
  then, manual browser smoke test for render-affecting changes.
- **Audit report**: Once S5U-287 lands, full-document audit runs as non-blocking
  CI step. Until then, run extraction on at least 5 representative pages and
  report any regressions in the PR description.

## 4. Golden Refresh and Threshold Change Rules

Golden fixtures and metric thresholds are governance-controlled. Silent changes
are prohibited.

### Golden Refresh Rules

1. **Never overwrite goldens silently.** A golden refresh must be an explicit,
   separate commit with prefix `S5U-XXX: refresh goldens` and a justification
   in the commit message.
2. **Include before/after metric diff.** The PR description must show the
   metric delta for every affected golden page. Once S5U-292 lands, use the
   guarded refresh tool (`atr golden-refresh --diff`).
3. **Golden refresh commits must not be mixed** with implementation commits.
   Keep them separate so reviewers can distinguish algorithmic changes from
   expectation updates.
4. **Every refreshed golden must link to the issue** that caused the change.

### Threshold Change Rules

1. **Thresholds live in config, not code.** All metric thresholds are in
   `configs/qa/thresholds.toml` (once S5U-281 creates it). Do not hardcode
   thresholds in test files or scripts.
2. **Loosening a threshold requires justification.** The PR description must
   explain why the previous threshold is no longer appropriate and link to the
   calibration data that supports the new value.
3. **Tightening a threshold is always allowed** without special governance, as
   long as CI passes.
4. **Threshold changes require the audit report** (once S5U-287 lands) to
   confirm the change does not mask regressions elsewhere.

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

Until the evaluation harness (S5U-274) and metric thresholds (S5U-281) are
implemented:

1. Run the pipeline on the walking skeleton fixture and at least 2 real pages.
2. Compare output artifacts against expected fixtures.
3. Report diffs in the PR description as a markdown table.

Once the evaluation harness exists:

1. Run `atr eval --golden-set core` and capture the summary.
2. Paste the before/after summary in the PR description.
3. If any metric degrades, explain why and whether it is acceptable.

## 7. Confidence Policy and Calibration Governance

Changes to confidence thresholds, routing bands, or block policies affect the
entire extraction pipeline and must be governed carefully.

### Confidence Bands (target state per S5U-293)

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

1. Run the full-document audit (S5U-287, once available) to produce calibration
   data.
2. Verify that the proposed change does not silently move pages between bands
   in unexpected ways.
3. Include a histogram or table in the PR showing page distribution across
   bands before and after the change.
4. If the change moves more than 10% of pages between bands, flag it for
   explicit human review.

## 8. CI/Helper-Script Enforcement Design

This section is a **design spec** for enforcement scripts to be implemented in
a follow-up issue. Some file paths referenced below (e.g., `configs/qa/`,
`scripts/check_extraction_scope.py`) do not exist yet and will be created by
the implementing issue. Once the scripts exist, the scripts themselves are the
source of truth; this section serves as the design intent.

### 8.1 Extraction Change Detector

**Script**: `scripts/check_extraction_scope.py`

**Purpose**: Detect whether a PR touches extraction-relevant files and
determine which checks are mandatory.

**Detection rules** (file path patterns):

```python
EXTRACTION_PATTERNS = {
    "schema": [
        "packages/schemas/python/atr_schemas/native_page_*",
        "packages/schemas/python/atr_schemas/layout_page_*",
        "packages/schemas/python/atr_schemas/page_ir_*",
        "packages/schemas/python/atr_schemas/asset_*",
        "packages/schemas/python/atr_schemas/symbol_*",
        "packages/schemas/python/atr_schemas/page_evidence_*",
        "packages/schemas/python/atr_schemas/resolved_page_*",
    ],
    "primitive_extraction": [
        "apps/pipeline/src/atr_pipeline/stages/extract_native/**",
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/**",
    ],
    "region_order": [
        "apps/pipeline/src/atr_pipeline/stages/structure/reading_order*",
        "apps/pipeline/src/atr_pipeline/stages/structure/region_*",
        "apps/pipeline/src/atr_pipeline/stages/structure/block_builder*",
        "apps/pipeline/src/atr_pipeline/stages/structure/real_block_builder*",
    ],
    "symbol_asset": [
        "apps/pipeline/src/atr_pipeline/stages/symbols/**",
        "packages/schemas/python/atr_schemas/symbol_*",
        "packages/schemas/python/atr_schemas/asset_*",
    ],
    "figure_callout_table": [
        "apps/pipeline/src/atr_pipeline/stages/structure/furniture*",
        "apps/pipeline/src/atr_pipeline/stages/structure/heuristics*",
    ],
    "confidence_routing": [
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/difficulty_*",
        "apps/pipeline/src/atr_pipeline/stages/extract_layout/fallback_*",
        "configs/qa/thresholds*",
    ],
    "golden_fixtures": [
        "packages/fixtures/**/expected/**",
    ],
    "thresholds": [
        "configs/qa/thresholds*",
    ],
}
```

**Output**: A JSON object mapping each detected change area to a list of
mandatory checks. Example:

```json
{
  "areas": ["primitive_extraction", "schema"],
  "mandatory_checks": [
    "unit_tests",
    "contract_tests",
    "invariant_checker",
    "golden_eval",
    "codegen_fresh"
  ],
  "golden_refresh_detected": false,
  "threshold_change_detected": false
}
```

### 8.2 Golden Refresh Guard

**Script**: `scripts/check_golden_refresh.py`

**Purpose**: Prevent silent golden overwrites.

**Logic**:

1. Parse `git diff --name-only` for files matching `packages/fixtures/**/expected/**`.
2. If golden files changed:
   a. Verify the golden changes are in dedicated commits (commit message
      contains `refresh goldens`).
   b. Verify the PR description contains a before/after metric diff section.
   c. If either check fails, exit non-zero with an actionable error message.

### 8.3 Threshold Loosening Guard

**Script**: `scripts/check_threshold_changes.py`

**Purpose**: Prevent silent threshold loosening.

**Logic**:

1. Parse `git diff` for changes to `configs/qa/thresholds.toml`.
2. For each changed threshold:
   a. Compare old and new values.
   b. If any threshold is loosened (value decreased for accuracy metrics,
      increased for error/leakage metrics), flag it.
   c. Require a justification comment in the diff (line starting with `#
      Justification:`) or a linked calibration report in the PR.

### 8.4 Mandatory Check Selector

**CI integration**: Add a step to `python-tests.yml` that runs
`check_extraction_scope.py` and conditionally enables additional CI jobs:

```yaml
# Proposed addition to .github/workflows/python-tests.yml
- name: Detect extraction scope
  id: extraction-scope
  run: |
    python scripts/check_extraction_scope.py \
      --base origin/main --head HEAD \
      --output-json /tmp/extraction-scope.json

- name: Golden refresh guard
  if: fromJSON(steps.extraction-scope.outputs.result).golden_refresh_detected
  run: python scripts/check_golden_refresh.py --base origin/main --head HEAD

- name: Threshold change guard
  if: fromJSON(steps.extraction-scope.outputs.result).threshold_change_detected
  run: python scripts/check_threshold_changes.py --base origin/main --head HEAD

- name: Extraction eval (golden set)
  if: contains(fromJSON(steps.extraction-scope.outputs.result).mandatory_checks, 'golden_eval')
  run: uv run atr eval --golden-set core --fail-on-threshold
```

### 8.5 Implementation Plan

The enforcement scripts should be implemented in this order:

1. `check_extraction_scope.py` — the foundation; determines what else runs.
2. `check_golden_refresh.py` — prevents the most common silent regression.
3. `check_threshold_changes.py` — prevents silent quality erosion.
4. CI workflow integration — wires the scripts into the existing pipeline.

Each script should be a standalone Python file under `scripts/`, runnable with
`uv run python scripts/<name>.py`, and testable with pytest. Target a follow-up
implementation issue for the actual code.

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

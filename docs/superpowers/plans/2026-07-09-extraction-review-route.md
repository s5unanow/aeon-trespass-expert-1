# Extraction Review Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lazy extraction-review route that drafts downloadable typed `patch_set.v1` JSON corrections for render-page artifacts.

**Architecture:** Keep patch construction in focused helpers under `apps/web/src/lib/patch-review/`, keep the route lazy in `router.tsx`, and add a small committed review fixture. The UI renders raw facsimile overlay and existing `BlockRenderer` output side-by-side while helpers produce JSON Pointer operations targeting the loaded render page.

**Tech Stack:** React 19, React Router 7, Vite/Vitest, Playwright, generated `@atr/schemas` TypeScript types, Python Pydantic contract tests.

## Global Constraints

Use generated schema types only for patch shapes.
Do not modify existing visual snapshots.
Do not add server upload or UI-side patch application.
Do not edit generated outputs manually.
Commit messages must start with `S5U-1540: `.

---

### Task 1: Patch Helper Tests And Implementation

**Files:**
- Create: `apps/web/src/lib/patch-review/paths.ts`
- Create: `apps/web/src/lib/patch-review/export.ts`
- Create: `apps/web/tests/component/patchReview.test.ts`

**Interfaces:**
- Produces: `buildBlockPath(blockIndex, ...tokens): string`, `buildTextCorrectionOperation(page, blockIndex, text)`, `buildReadingOrderOperation(page, blockIndex, direction)`, `buildSuppressBlockOperation(page, blockIndex)`, `buildPatchSet(input)`, `buildPatchFilename(patchSet, ids)`, `downloadPatchSet(patchSet, ids)`.

- [ ] Write failing Vitest coverage for pointer escaping, block-index guards, text correction, reading-order move, block suppression, author/reason export guards, generated type assignment, and JSON Schema validation.
- [ ] Run the focused Vitest file and confirm it fails because helpers do not exist.
- [ ] Implement helper modules with generated schema types from `@atr/schemas`.
- [ ] Run the focused Vitest file and confirm it passes.

### Task 2: Review Route UI

**Files:**
- Modify: `apps/web/src/app/router.tsx`
- Create: `apps/web/src/routes/ExtractionReviewPage.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Consumes helpers from Task 1 and `loadRenderPage`.
- Produces a lazy route at `/documents/:documentId/:edition/review/:pageId`.

- [ ] Write component/e2e expectations for route loading, selection sync, blocked export, text correction drafting, download, and persistence.
- [ ] Run focused tests and confirm they fail because the route does not exist.
- [ ] Add the lazy route and review UI.
- [ ] Add scoped CSS classes for review layout, overlay, block highlights, correction panel, and patch drawer.
- [ ] Run focused tests and confirm they pass.

### Task 3: Fixtures And Pipeline Contract

**Files:**
- Create: `apps/web/public/documents/review_fixture/en/manifest.json`
- Create: `apps/web/public/documents/review_fixture/en/data/render_page.p0001.json`
- Create: `apps/web/public/documents/review_fixture/images/review-page.svg`
- Create: `packages/fixtures/sample_documents/review_fixture/expected/render_page.p0001.json`
- Create: `packages/fixtures/sample_documents/review_fixture/patches/render/patch-review-fixture.json`
- Create: `apps/pipeline/tests/unit/stages/patch/test_review_route_contract.py`

**Interfaces:**
- The patch fixture must match the UI export shape and apply cleanly to the corresponding render fixture.

- [ ] Write a failing Python test that parses the UI-shaped patch, applies it with `apply_patches`, and validates `RenderPageV1`.
- [ ] Run the focused Python test and confirm it fails before the fixture exists.
- [ ] Add the review fixture and patch fixture.
- [ ] Run the focused Python test and confirm it passes.

### Task 4: Full Verification And PR

**Files:**
- Create: `tmp/review-s5u-1540.md`

- [ ] Run `make check`.
- [ ] Run `pnpm --dir apps/web test:e2e`.
- [ ] Perform Path B self-review and write `tmp/review-s5u-1540.md`.
- [ ] Commit with an `S5U-1540: ` message containing red-before evidence.
- [ ] Push branch and open a draft PR with `gh pr create --draft`, including `Closes S5U-1540`.

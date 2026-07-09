# Extraction Review Route Design

## Scope

Build a lazy reader route at `/documents/:documentId/:edition/review/:pageId` where a reviewer can inspect a committed render-page payload, select a block, draft typed `patch_set.v1` operations, persist draft state locally, and download schema-shaped JSON for later pipeline ingestion.

## Architecture

The route stays outside the normal reader bundle by lazy-loading a new `ExtractionReviewPage`. It uses `loadRenderPage` for normalized rendering and an additional raw JSON fetch for JSON Pointer paths that must resolve against the original `render_page.{pageId}.json` artifact. Shared patch helpers in `apps/web/src/lib/patch-review/` build pointers, validate block indices, create generated-schema `PatchSetV1` values, and compute filenames.

## UI

The page uses a two-column work surface: a raster facsimile with bbox overlays on the left and rendered `BlockRenderer` blocks on the right. Hovering or clicking either surface highlights the matching block. Selecting a block opens correction controls for three MVP scopes: text replacement of the first text inline, reading-order moves by moving a block earlier or later in `/blocks`, and block suppression by deleting `/blocks/{index}`.

## Patch Artifact Rules

All patch data is typed with generated `@atr/schemas` `PatchSetV1` and related generated unions. The UI never mutates render JSON and never uploads patches. Export is blocked until there is an author, a non-empty reason, and at least one valid operation. Provenance includes author, ISO timestamp, and source confidence when present in page metadata.

## Persistence

Draft state is saved to localStorage under a document/edition/page key and restored on reload. Only editable draft state is stored; export-time timestamps and patch IDs are generated fresh.

## Verification

Vitest covers JSON Pointer construction, ordering operations, export shape, schema validation, and guards. Playwright covers selecting a block, drafting a text correction, and receiving a downloaded patch JSON. A Python contract test validates the UI-shaped fixture patch with `PatchSetV1`, applies it through `apply_patches`, and validates the resulting `RenderPageV1`.

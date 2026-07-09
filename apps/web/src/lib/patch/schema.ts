// Patch drafting for extraction review (S5U-1538).
//
// The canonical contract lives in Pydantic
// (`packages/schemas/python/atr_schemas/patch_set_v1.py`) and the
// TypeScript types are generated from the JSON Schema (see `make codegen`).
// The pipeline applicator (`apps/pipeline/src/atr_pipeline/stages/patch/applicator.py`)
// consumes the same model.
//
// This module holds the schema-version literal, filename helper, and
// a narrow exported type alias for the UI draft state.

import type {
  patchSetV1,
  PatchSetV1,
  PatchOperation,
  PatchProvenance,
  PatchScope,
  PatchTargetKind,
} from '@atr/schemas';

export type PatchDraft = PatchSetV1;
export type PatchOp = PatchOperation;
export type { PatchProvenance, PatchScope, PatchTargetKind };

export const PATCH_SCHEMA_VERSION = 'patch_set.v1' as const;
export const PATCH_TARGET_KIND = 'render_page' as const satisfies PatchTargetKind;

export function buildPatchFilename(patch: PatchDraft): string {
  const safeTs = (patch.created_at ?? new Date().toISOString())
    .replace(/[:.]/g, '-');
  const doc = patch.target_artifact_ref || 'unknown';
  // Prefer stable ids; fall back to patch_id fragments if needed.
  // Filename pattern per spec: patch-{document_id}-{edition}-{page_id}-{timestamp}.json
  // We derive document/edition/page from patch_id convention or leave placeholders
  // when not embedded; callers usually supply a fully populated patch_id.
  return `patch-${doc}-${safeTs}.json`;
}

// Helper to build a minimal valid PatchSetV1 skeleton for a page.
export function createEmptyPatchSet(params: {
  documentId: string;
  edition: string;
  pageId: string;
  author?: string;
}): PatchDraft {
  const ts = new Date().toISOString();
  const patchId = `review-${params.documentId}-${params.edition}-${params.pageId}-${ts.replace(/[:.]/g, '')}`;
  return {
    schema_version: PATCH_SCHEMA_VERSION,
    patch_id: patchId,
    target_artifact_ref: `${params.documentId}/${params.edition}/data/render_page.${params.pageId}.json`,
    target_kind: PATCH_TARGET_KIND,
    operations: [],
    reason: '',
    author: params.author ?? '',
    provenance: {
      author: params.author ?? '',
      created_at: ts,
      source_confidence: null,
      expected_confidence_delta: null,
    },
  };
}

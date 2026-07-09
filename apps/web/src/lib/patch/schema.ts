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
} from '@atr/schemas';

export type PatchDraft = PatchSetV1;
export type PatchOp = patchSetV1.PatchOperation;
export type PatchProvenance = patchSetV1.PatchProvenance;
export type PatchScope = patchSetV1.PatchScope;
export type PatchTargetKind = patchSetV1.PatchTargetKind;

export const PATCH_SCHEMA_VERSION = 'patch_set.v1' as const;
export const PATCH_TARGET_KIND = 'render_page' as const satisfies PatchTargetKind;

export function buildPatchFilename(patch: PatchDraft): string {
  const ts = patch.provenance?.created_at ?? new Date().toISOString();
  const safeTs = (typeof ts === 'string' ? ts : new Date().toISOString()).replace(/[:.]/g, '-');
  const doc = (patch.target_artifact_ref || patch.patch_id || 'unknown').replace(/[^a-zA-Z0-9._-]/g, '_');
  // Filename pattern per spec: patch-{document_id}-{edition}-{page_id}-{timestamp}.json
  // We embed a compact id; the real doc/edition/page are derivable from target_artifact_ref or caller.
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
      created_at: ts as any, // matches generated CreatedAt (string | null)
      source_confidence: null,
      expected_confidence_delta: null,
    },
  };
}

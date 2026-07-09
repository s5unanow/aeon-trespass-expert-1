// localStorage-backed draft persistence for the review route.
// Keyed by document/edition/page so reloads on the same review URL restore ops.

import type { PatchDraft, PatchOp } from './schema';
import { createEmptyPatchSet } from './schema';

const STORAGE_PREFIX = 'patch-draft-';

function storageKey(documentId: string, edition: string, pageId: string): string {
  return `${STORAGE_PREFIX}${documentId}:${edition}:${pageId}`;
}

export function loadDraft(
  documentId: string,
  edition: string,
  pageId: string,
): PatchDraft | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(storageKey(documentId, edition, pageId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PatchDraft;
    // Basic shape guard; full validation happens on export.
    if (!parsed || !Array.isArray(parsed.operations) || typeof parsed.patch_id !== 'string') {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveDraft(
  documentId: string,
  edition: string,
  pageId: string,
  draft: PatchDraft,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      storageKey(documentId, edition, pageId),
      JSON.stringify(draft),
    );
  } catch {
    // Quota or private mode — draft loss is acceptable (non-fatal).
  }
}

export function clearDraft(documentId: string, edition: string, pageId: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(storageKey(documentId, edition, pageId));
  } catch {
    /* ignore */
  }
}

// Merge a loaded (or empty) draft with new ops while preserving metadata.
export function ensureDraftForPage(params: {
  documentId: string;
  edition: string;
  pageId: string;
  initialAuthor?: string;
  loadedPageMeta?: { confidence?: number | null };
}): PatchDraft {
  const existing = loadDraft(params.documentId, params.edition, params.pageId);
  if (existing) {
    // Backfill provenance if missing
    if (!existing.provenance) {
      existing.provenance = {
        author: existing.author || params.initialAuthor || '',
        created_at: new Date().toISOString(),
        source_confidence: params.loadedPageMeta?.confidence ?? null,
        expected_confidence_delta: null,
      };
    }
    return existing;
  }
  const fresh = createEmptyPatchSet({
    documentId: params.documentId,
    edition: params.edition,
    pageId: params.pageId,
    author: params.initialAuthor,
  });
  if (params.loadedPageMeta?.confidence != null) {
    fresh.provenance = {
      ...fresh.provenance,
      source_confidence: params.loadedPageMeta.confidence,
    } as any;
  }
  return fresh;
}

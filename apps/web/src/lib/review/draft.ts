/**
 * Review draft view-models + localStorage persistence.
 *
 * A `DraftEntry` is a UI wrapper around a generated `PatchOperation` (the thing
 * that gets exported) plus the metadata the drawer needs: the per-correction
 * `reason`, the block it targets, and a display summary. The wrapper is a
 * view-model — the exported patch shapes still come only from `@atr/schemas`.
 *
 * Drafts survive reload: they are keyed by document/edition/page so switching
 * pages never leaks one page's corrections into another.
 */

import type { PatchOperation, ReviewScope } from './operations';

export interface DraftEntry {
  /** Stable id for React keys / removal. */
  id: string;
  scope: ReviewScope;
  /** `block.id` the correction targets (drives facsimile↔list sync + display). */
  blockRef: string;
  /** Index into the page's blocks — used for out-of-bounds guarding on export. */
  blockIndex: number;
  /** Per-correction reason (required before it can be added). */
  reason: string;
  /** One-line human summary shown in the drawer. */
  summary: string;
  /** The generated patch operation that will be exported. */
  operation: PatchOperation;
}

export interface ReviewDraft {
  author: string;
  entries: DraftEntry[];
}

export function emptyDraft(): ReviewDraft {
  return { author: '', entries: [] };
}

let entryCounter = 0;

/** Monotonic, collision-free id for a draft entry within a session. */
export function nextEntryId(scope: ReviewScope): string {
  entryCounter += 1;
  return `${scope}-${entryCounter}`;
}

export function draftStorageKey(documentId: string, edition: string, pageId: string): string {
  return `atr-review-draft:${documentId}:${edition}:${pageId}`;
}

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    // Access to localStorage can throw (privacy mode / disabled storage).
    return null;
  }
}

/** Load a persisted draft; returns an empty draft on miss or malformed data. */
export function loadDraft(key: string): ReviewDraft {
  const store = storage();
  if (!store) return emptyDraft();
  const raw = store.getItem(key);
  if (!raw) return emptyDraft();
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return emptyDraft();
    const obj = parsed as Partial<ReviewDraft>;
    const author = typeof obj.author === 'string' ? obj.author : '';
    const entries = Array.isArray(obj.entries) ? (obj.entries as DraftEntry[]) : [];
    return { author, entries };
  } catch {
    return emptyDraft();
  }
}

/** Persist a draft. Best-effort — a storage failure must not break drafting. */
export function saveDraft(key: string, draft: ReviewDraft): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(key, JSON.stringify(draft));
  } catch {
    // Quota / disabled storage — drafting continues in-memory only.
  }
}

/** Remove a persisted draft (e.g. after a successful export). */
export function clearDraft(key: string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(key);
  } catch {
    // ignore
  }
}

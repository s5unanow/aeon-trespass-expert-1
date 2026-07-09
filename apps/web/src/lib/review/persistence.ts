import type { patchSetV1, PatchSetV1 } from '@atr/schemas';
import { normalizeRenderPage } from '../render/normalize';
import type { RenderPageData } from '../render/types';
import { applyPatchOperations } from './patches';

export type ReviewDraft = Required<Pick<PatchSetV1, 'operations' | 'reason' | 'author'>>;

const EMPTY_DRAFT: ReviewDraft = { operations: [], reason: '', author: '' };
const PATCH_OPS = new Set(['replace', 'insert', 'delete']);
const PATCH_SCOPES = new Set<patchSetV1.PatchScope>([
  'text',
  'block_structure',
  'reading_order',
  'region_assignment',
  'asset_link',
  'symbol_resolution',
  'confidence_override',
  'fallback_resolution',
]);

export function reviewStorageKey(documentId: string, edition: string, pageId: string): string {
  return ['atr', 'extraction-review', documentId, edition, pageId]
    .map(encodeURIComponent)
    .join(':');
}

export function saveReviewDraft(key: string, draft: ReviewDraft): void {
  localStorage.setItem(key, JSON.stringify(draft));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isOperation(value: unknown): value is patchSetV1.PatchOperation {
  if (
    !isObject(value) ||
    typeof value.op !== 'string' ||
    !PATCH_OPS.has(value.op) ||
    typeof value.path !== 'string' ||
    !value.path.startsWith('/')
  ) {
    return false;
  }
  return (
    value.scope === undefined ||
    value.scope === null ||
    (typeof value.scope === 'string' && PATCH_SCOPES.has(value.scope as patchSetV1.PatchScope))
  );
}

export function loadReviewDraft(key: string, target: RenderPageData): ReviewDraft {
  const stored = localStorage.getItem(key);
  if (stored === null) return { ...EMPTY_DRAFT };
  try {
    const parsed: unknown = JSON.parse(stored);
    if (
      !isObject(parsed) ||
      !Array.isArray(parsed.operations) ||
      !parsed.operations.every(isOperation) ||
      typeof parsed.reason !== 'string' ||
      typeof parsed.author !== 'string'
    ) {
      return { ...EMPTY_DRAFT };
    }
    normalizeRenderPage(applyPatchOperations(target, parsed.operations));
    return { operations: parsed.operations, reason: parsed.reason, author: parsed.author };
  } catch {
    return { ...EMPTY_DRAFT };
  }
}

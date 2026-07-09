import type { patchSetV1, PatchSetV1 } from '@atr/schemas';
import type { RenderBlock } from '../render/types';

type PatchOperation = patchSetV1.PatchOperation;
type PatchValue = patchSetV1.PatchValue;

function decodePointerToken(token: string): string {
  return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

function arrayIndex(token: string, length: number): number {
  if (!/^\d+$/.test(token)) throw new Error(`Invalid array index: ${token}`);
  const index = Number(token);
  if (!Number.isSafeInteger(index) || index < 0 || index >= length) {
    throw new Error(`Array index ${token} is out of bounds`);
  }
  return index;
}

export function resolvePointer(root: unknown, pointer: string): unknown {
  if (pointer === '') return root;
  if (!pointer.startsWith('/')) throw new Error(`JSON Pointer must start with "/": ${pointer}`);
  const tokens = pointer.slice(1).split('/').map(decodePointerToken);
  let current = root;
  for (const token of tokens) {
    if (Array.isArray(current)) {
      current = current[arrayIndex(token, current.length)];
      continue;
    }
    if (current !== null && typeof current === 'object') {
      if (!Object.prototype.hasOwnProperty.call(current, token)) {
        throw new Error(`JSON Pointer property does not exist: ${token}`);
      }
      current = (current as Record<string, unknown>)[token];
      continue;
    }
    throw new Error(`JSON Pointer cannot traverse through ${typeof current}`);
  }
  return current;
}

function requireBlock(blocks: RenderBlock[], blockIndex: number): RenderBlock {
  if (!Number.isInteger(blockIndex) || blockIndex < 0 || blockIndex >= blocks.length) {
    throw new Error(`Block index ${blockIndex} is out of bounds`);
  }
  return blocks[blockIndex];
}

export function buildTextOperation(
  blocks: RenderBlock[],
  blockIndex: number,
  inlineIndex: number,
  correctedText: string,
): PatchOperation {
  const block = requireBlock(blocks, blockIndex);
  if (!('children' in block) || !Array.isArray(block.children)) {
    throw new Error(`Block ${block.id} has no editable inline children`);
  }
  if (!Number.isInteger(inlineIndex) || inlineIndex < 0 || inlineIndex >= block.children.length) {
    throw new Error(`Inline index ${inlineIndex} is out of bounds for block ${block.id}`);
  }
  const inline = block.children[inlineIndex];
  if (!('kind' in inline) || inline.kind !== 'text') {
    throw new Error(`Inline index ${inlineIndex} is not a text inline`);
  }
  if (correctedText.trim() === '') throw new Error('Corrected text must not be empty');
  return {
    op: 'replace',
    path: `/blocks/${blockIndex}/children/${inlineIndex}/text`,
    value: correctedText,
    scope: 'text',
  };
}

function toPatchValue(value: unknown): PatchValue {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value))
  ) {
    return value;
  }
  if (Array.isArray(value)) return value.map(toPatchValue);
  if (typeof value === 'object') {
    const output: Record<string, PatchValue> = {};
    for (const [key, child] of Object.entries(value)) {
      if (child !== undefined) output[key] = toPatchValue(child);
    }
    return output;
  }
  throw new Error(`Patch value is not JSON-serializable: ${typeof value}`);
}

export function buildReadingOrderOperation(
  blocks: RenderBlock[],
  blockIndex: number,
  direction: 'earlier' | 'later',
): PatchOperation {
  requireBlock(blocks, blockIndex);
  if (direction === 'earlier' && blockIndex === 0) throw new Error('Block is already first');
  if (direction === 'later' && blockIndex === blocks.length - 1) {
    throw new Error('Block is already last');
  }
  const targetIndex = direction === 'earlier' ? blockIndex - 1 : blockIndex + 1;
  const reordered = blocks.slice();
  [reordered[blockIndex], reordered[targetIndex]] = [reordered[targetIndex], reordered[blockIndex]];
  return {
    op: 'replace',
    path: '/blocks',
    value: toPatchValue(reordered),
    scope: 'reading_order',
  };
}

export function buildSuppressOperation(blocks: RenderBlock[], blockIndex: number): PatchOperation {
  requireBlock(blocks, blockIndex);
  return { op: 'delete', path: `/blocks/${blockIndex}`, scope: 'block_structure' };
}

function safeTimestamp(date: Date): string {
  return date.toISOString().replace(/[:.]/g, '-');
}

export function buildPatchSet(
  documentId: string,
  edition: string,
  pageId: string,
  operations: PatchOperation[],
  reason: string,
  author: string,
  sourceConfidence: number | null,
  createdAt: Date,
): PatchSetV1 {
  if (operations.length === 0) throw new Error('Add at least one patch operation before export');
  const trimmedReason = reason.trim();
  if (trimmedReason === '') throw new Error('Patch reason is required before export');
  const trimmedAuthor = author.trim();
  if (trimmedAuthor === '') throw new Error('Patch author is required before export');
  if (
    sourceConfidence !== null &&
    (!Number.isFinite(sourceConfidence) || sourceConfidence < 0 || sourceConfidence > 1)
  ) {
    throw new Error('Source confidence must be between 0 and 1');
  }
  const timestamp = safeTimestamp(createdAt);
  const provenance = {
    author: trimmedAuthor,
    created_at: createdAt.toISOString(),
    ...(sourceConfidence === null ? {} : { source_confidence: sourceConfidence }),
  } satisfies patchSetV1.PatchProvenance;
  return {
    schema_version: 'patch_set.v1',
    patch_id: `patch-${documentId}-${edition}-${pageId}-${timestamp}`,
    target_artifact_ref: `documents/${documentId}/${edition}/data/render_page.${pageId}.json`,
    target_kind: 'render_page',
    operations,
    reason: trimmedReason,
    author: trimmedAuthor,
    provenance,
  } satisfies PatchSetV1;
}

export function buildPatchFilename(patchSet: PatchSetV1): string {
  return `${patchSet.patch_id}.json`;
}

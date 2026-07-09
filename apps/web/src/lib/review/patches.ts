import type { patchSetV1, PatchSetV1 } from '@atr/schemas';
import { normalizeRenderPage } from '../render/normalize';
import type { RenderPageData } from '../render/types';
import type { RenderBlock } from '../render/types';

type PatchOperation = patchSetV1.PatchOperation;
type PatchValue = patchSetV1.PatchValue;

function decodePointerToken(token: string): string {
  return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

function pointerTokens(pointer: string): string[] {
  if (!pointer.startsWith('/')) throw new Error(`JSON Pointer must start with "/": ${pointer}`);
  if (pointer === '/') return [''];
  return pointer.slice(1).split('/').map(decodePointerToken);
}

function arrayIndex(token: string, length: number): number {
  if (!/^\d+$/.test(token)) throw new Error(`Invalid array index: ${token}`);
  const index = Number(token);
  if (!Number.isSafeInteger(index) || index < 0 || index >= length) {
    throw new Error(`Array index ${token} is out of bounds`);
  }
  return index;
}

function resolveTokens(root: unknown, tokens: string[]): unknown {
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

export function resolvePointer(root: unknown, pointer: string): unknown {
  if (pointer === '') return root;
  return resolveTokens(root, pointerTokens(pointer));
}

function resolveParent(root: unknown, pointer: string): { parent: unknown; key: string } {
  const tokens = pointerTokens(pointer);
  if (tokens.length === 0) throw new Error('Patch path must not be empty');
  const key = tokens.pop();
  if (key === undefined) throw new Error('Patch path must identify a value');
  return { parent: resolveTokens(root, tokens), key };
}

function requireOperationValue(operation: PatchOperation): PatchValue {
  if (!Object.prototype.hasOwnProperty.call(operation, 'value')) {
    throw new Error(`${operation.op} operation at ${operation.path} requires a value`);
  }
  return operation.value ?? null;
}

function isSameJsonValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function replaceAtPointer(root: unknown, operation: PatchOperation): void {
  const value = requireOperationValue(operation);
  const existing = resolvePointer(root, operation.path);
  if (isSameJsonValue(existing, value)) {
    throw new Error(`Patch operation at ${operation.path} does not change the target`);
  }
  const { parent, key } = resolveParent(root, operation.path);
  if (Array.isArray(parent)) {
    parent[arrayIndex(key, parent.length)] = value;
    return;
  }
  if (parent !== null && typeof parent === 'object') {
    (parent as Record<string, unknown>)[key] = value;
    return;
  }
  throw new Error(`JSON Pointer cannot mutate through ${typeof parent}`);
}

function deleteAtPointer(root: unknown, operation: PatchOperation): void {
  resolvePointer(root, operation.path);
  const { parent, key } = resolveParent(root, operation.path);
  if (Array.isArray(parent)) {
    parent.splice(arrayIndex(key, parent.length), 1);
    return;
  }
  if (parent !== null && typeof parent === 'object') {
    delete (parent as Record<string, unknown>)[key];
    return;
  }
  throw new Error(`JSON Pointer cannot delete through ${typeof parent}`);
}

function insertAtPointer(root: unknown, operation: PatchOperation): void {
  const value = requireOperationValue(operation);
  const { parent, key } = resolveParent(root, operation.path);
  if (!Array.isArray(parent)) throw new Error('Insert operation requires an array target');
  if (!/^\d+$/.test(key)) throw new Error(`Invalid array index: ${key}`);
  const index = Number(key);
  if (!Number.isSafeInteger(index) || index < 0 || index > parent.length) {
    throw new Error(`Array index ${key} is out of bounds`);
  }
  parent.splice(index, 0, value);
}

function validateReviewOperationShape(operation: PatchOperation): void {
  if (operation.scope === 'text') {
    if (
      operation.op !== 'replace' ||
      !/^\/blocks\/\d+\/children\/\d+\/text$/.test(operation.path) ||
      typeof operation.value !== 'string' ||
      operation.value.trim() === ''
    ) {
      throw new Error('Text operations must replace a non-empty block-inline text value');
    }
    return;
  }
  if (operation.scope === 'reading_order') {
    if (
      operation.op !== 'replace' ||
      operation.path !== '/blocks' ||
      !Array.isArray(operation.value)
    ) {
      throw new Error('Reading-order operations must replace the blocks array');
    }
    return;
  }
  if (operation.scope === 'block_structure') {
    if (operation.op !== 'delete' || !/^\/blocks\/\d+$/.test(operation.path)) {
      throw new Error('Block-structure operations must delete one block');
    }
    return;
  }
  throw new Error(`Unsupported review patch scope: ${operation.scope ?? 'missing'}`);
}

/** Apply operations only to an in-memory draft so later pointers compose safely. */
export function applyPatchOperations<T>(target: T, operations: PatchOperation[]): T {
  const projected = structuredClone(target) as unknown;
  for (const operation of operations) {
    validateReviewOperationShape(operation);
    if (operation.path === '') throw new Error('Patch path must not be empty');
    if (operation.op === 'replace') replaceAtPointer(projected, operation);
    else if (operation.op === 'delete') deleteAtPointer(projected, operation);
    else if (operation.op === 'insert') insertAtPointer(projected, operation);
    else throw new Error(`Unsupported patch operation: ${operation.op}`);
  }
  return projected as T;
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
  if (correctedText === inline.text) throw new Error('Corrected text must change the target');
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

/** Positional operations form a dependency chain, so removal is stack-like. */
export function removeOperationAndDependents(
  operations: PatchOperation[],
  operationIndex: number,
): PatchOperation[] {
  if (
    !Number.isInteger(operationIndex) ||
    operationIndex < 0 ||
    operationIndex >= operations.length
  ) {
    throw new Error(`Operation index ${operationIndex} is out of bounds`);
  }
  return operations.slice(0, operationIndex);
}

function safeTimestamp(date: Date): string {
  return date.toISOString().replace(/[:.]/g, '-');
}

function validateTargetArtifactRef(
  targetArtifactRef: string,
  documentId: string,
  pageId: string,
): void {
  const parts = targetArtifactRef.split('/');
  const filename = parts[4] ?? '';
  if (
    parts.length !== 5 ||
    parts[0] !== documentId ||
    parts[1] !== 'render_page.v1' ||
    parts[2] !== 'page' ||
    parts[3] !== pageId ||
    !/^[^/]+\.json$/.test(filename)
  ) {
    throw new Error('Target artifact ref is not an ingestible render-page artifact');
  }
}

export function buildPatchSet(
  documentId: string,
  edition: string,
  pageId: string,
  targetArtifactRef: string,
  target: RenderPageData,
  operations: PatchOperation[],
  reason: string,
  author: string,
  sourceConfidence: number | null,
  createdAt: Date,
): PatchSetV1 {
  if (operations.length === 0) throw new Error('Add at least one patch operation before export');
  validateTargetArtifactRef(targetArtifactRef, documentId, pageId);
  normalizeRenderPage(applyPatchOperations(target, operations));
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
    target_artifact_ref: targetArtifactRef,
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

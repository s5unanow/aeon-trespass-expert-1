import type { PatchSetV1, patchSetV1 } from '@atr/schemas';
import type { RenderBlock, RenderPageData, RenderTextInline } from '../render/types';
import { buildBlockPath, resolveJsonPointer } from './paths';

export { buildBlockPath, resolveJsonPointer };

export type ReviewPatchOperation = patchSetV1.PatchOperation;
export type ReadingOrderDirection = 'earlier' | 'later';

export interface BuildPatchSetInput {
  documentId: string;
  edition: string;
  pageId: string;
  page: RenderPageData;
  operations: ReviewPatchOperation[];
  author: string;
  reason: string;
  sourceConfidence?: number | null;
  now?: Date;
}

function assertBlockIndex(page: RenderPageData, blockIndex: number): void {
  if (!Number.isInteger(blockIndex) || blockIndex < 0 || blockIndex >= page.blocks.length) {
    throw new Error(`Block index out of bounds: ${blockIndex}`);
  }
}

function firstTextInline(block: RenderBlock): { inline: RenderTextInline; index: number } {
  if (!('children' in block)) {
    throw new Error(`Block ${block.id} has no inline children`);
  }
  const index = block.children.findIndex((child) => child.kind === 'text');
  if (index < 0) {
    throw new Error(`Block ${block.id} has no text inline`);
  }
  return { inline: block.children[index] as RenderTextInline, index };
}

function asPatchValue(value: object): patchSetV1.Value {
  return value as patchSetV1.Value;
}

function safeTimestamp(date: Date): string {
  return date.toISOString().replace(/[:.]/g, '-');
}

export function buildTextCorrectionOperation(
  page: RenderPageData,
  blockIndex: number,
  correctedText: string,
): ReviewPatchOperation {
  assertBlockIndex(page, blockIndex);
  const block = page.blocks[blockIndex];
  const { inline, index } = firstTextInline(block);
  return {
    op: 'replace',
    path: buildBlockPath(blockIndex, 'children', index),
    value: asPatchValue({ kind: 'text', text: correctedText, marks: inline.marks }),
    scope: 'text',
  };
}

export function buildReadingOrderOperations(
  page: RenderPageData,
  blockIndex: number,
  direction: ReadingOrderDirection,
): ReviewPatchOperation[] {
  assertBlockIndex(page, blockIndex);
  const targetIndex = direction === 'earlier' ? blockIndex - 1 : blockIndex + 1;
  if (targetIndex < 0 || targetIndex >= page.blocks.length) {
    throw new Error(`Cannot move block ${direction}: already at page boundary`);
  }
  return [
    { op: 'delete', path: buildBlockPath(blockIndex), scope: 'reading_order' },
    {
      op: 'insert',
      path: buildBlockPath(targetIndex),
      value: asPatchValue(page.blocks[blockIndex]),
      scope: 'reading_order',
    },
  ];
}

export function buildSuppressBlockOperation(
  page: RenderPageData,
  blockIndex: number,
): ReviewPatchOperation {
  assertBlockIndex(page, blockIndex);
  return {
    op: 'delete',
    path: buildBlockPath(blockIndex),
    scope: 'block_structure',
  };
}

export function buildPatchSet(input: BuildPatchSetInput): PatchSetV1 {
  const author = input.author.trim();
  const reason = input.reason.trim();
  if (!author) throw new Error('Patch author is required before export');
  if (!reason) throw new Error('Patch reason is required before export');
  if (input.operations.length === 0) {
    throw new Error('At least one patch operation is required before export');
  }
  const now = input.now ?? new Date();
  return {
    schema_version: 'patch_set.v1',
    patch_id: `patch-${input.documentId}-${input.edition}-${input.pageId}-${safeTimestamp(now)}`,
    target_artifact_ref: `documents/${input.documentId}/${input.edition}/data/render_page.${input.pageId}.json`,
    target_kind: 'render_page',
    operations: input.operations,
    reason,
    author,
    provenance: {
      author,
      created_at: now.toISOString(),
      source_confidence: input.sourceConfidence ?? null,
      expected_confidence_delta: null,
    },
  };
}

export function buildPatchFilename(
  patchSet: PatchSetV1,
  documentId: string,
  edition: string,
  pageId: string,
): string {
  const createdAt = patchSet.provenance?.created_at ?? new Date().toISOString();
  return `patch-${documentId}-${edition}-${pageId}-${createdAt.replace(/[:.]/g, '-')}.json`;
}

export function downloadPatchSet(
  patchSet: PatchSetV1,
  documentId: string,
  edition: string,
  pageId: string,
): void {
  const json = JSON.stringify(patchSet, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildPatchFilename(patchSet, documentId, edition, pageId);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

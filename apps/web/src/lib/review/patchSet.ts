/**
 * Assemble a downloadable `patch_set.v1` from a review draft, plus the export
 * guards. The exported object is typed as the generated `PatchSetV1`, so the
 * compiler enforces the contract; a companion vitest test additionally
 * validates a built export against the JSON Schema.
 */

import type { PatchSetV1 } from '@atr/schemas';
import type { RenderBlock, RenderInlineNode, RenderPageData } from '../render/types';
import type { DraftEntry, ReviewDraft } from './draft';

const SCHEMA_VERSION = 'patch_set.v1' as const;
const TARGET_KIND = 'render_page' as const;

export interface BuildPatchSetInput {
  documentId: string;
  edition: string;
  pageId: string;
  draft: ReviewDraft;
  /** Page confidence before patch, when the render page carries one. */
  sourceConfidence?: number | null;
  /** Injectable clock for deterministic tests. */
  now?: Date;
}

/** `render_page.{pageId}.json` reference for the patch's `target_artifact_ref`. */
export function targetArtifactRef(documentId: string, edition: string, pageId: string): string {
  return `${documentId}/${edition}/data/render_page.${pageId}.json`;
}

/** Downloaded filename — mirrors `lib/feedback` (`patch-{doc}-{ed}-{page}-{ts}.json`). */
export function buildPatchFilename(input: BuildPatchSetInput): string {
  const ts = (input.now ?? new Date()).toISOString().replace(/[:.]/g, '-');
  return `patch-${input.documentId}-${input.edition}-${input.pageId}-${ts}.json`;
}

/**
 * Build the exportable `PatchSetV1`. The set-level `reason` is the joined list
 * of per-correction reasons (each entry requires its own reason before it can
 * be added), so the "per-patch reason" survives into the single schema field.
 */
export function buildPatchSet(input: BuildPatchSetInput): PatchSetV1 {
  const now = input.now ?? new Date();
  const author = input.draft.author.trim();
  const reasons = input.draft.entries.map((e) => e.reason.trim()).filter(Boolean);
  return {
    schema_version: SCHEMA_VERSION,
    patch_id: `${input.documentId}-${input.edition}-${input.pageId}-${now.toISOString()}`,
    target_artifact_ref: targetArtifactRef(input.documentId, input.edition, input.pageId),
    target_kind: TARGET_KIND,
    operations: input.draft.entries.map((e) => e.operation),
    reason: reasons.join('; '),
    author,
    provenance: {
      author,
      created_at: now.toISOString(),
      source_confidence: input.sourceConfidence ?? null,
    },
  };
}

/**
 * Export guards (acceptance #4 + "reject out-of-bounds block indices and empty
 * operations before export"). Returns a list of human-readable errors; an
 * empty list means the draft is safe to export.
 */
export function collectExportErrors(draft: ReviewDraft, page: RenderPageData): string[] {
  const errors: string[] = [];
  if (draft.entries.length === 0) {
    errors.push('Add at least one correction before exporting.');
  }
  if (draft.author.trim() === '') {
    errors.push('Author is required.');
  }
  draft.entries.forEach((entry, i) => {
    if (!isBlockIndexInBounds(entry.blockIndex, page)) {
      errors.push(
        `Correction ${i + 1} targets block #${entry.blockIndex}, which is out of range ` +
          `(page has ${page.blocks.length} blocks).`,
      );
    }
    if (entry.reason.trim() === '') {
      errors.push(`Correction ${i + 1} (${entry.scope}) is missing a reason.`);
    }
  });
  return errors;
}

export function isBlockIndexInBounds(blockIndex: number, page: RenderPageData): boolean {
  return Number.isInteger(blockIndex) && blockIndex >= 0 && blockIndex < page.blocks.length;
}

/**
 * The first editable text inline of a block, or null when there is none.
 *
 * Returns the inline's index **into the raw `children` array** so the built
 * pointer resolves in the artifact JSON. Table blocks (nested row/cell
 * children) and dividers have no directly-editable inline and return null —
 * table-cell text correction is a follow-up (S5U-787).
 */
export function firstEditableText(block: RenderBlock): { inlineIndex: number; text: string } | null {
  if (block.kind === 'table' || block.kind === 'divider') return null;
  const idx = block.children.findIndex((c) => c.kind === 'text');
  if (idx < 0) return null;
  const child = block.children[idx];
  return child.kind === 'text' ? { inlineIndex: idx, text: child.text } : null;
}

/**
 * Concatenated visible text of a block (text inlines joined by spaces).
 * Tables (nested row children) and dividers have no top-level inline text and
 * return `""` — table-cell text is a follow-up (S5U-787).
 */
export function blockPlainText(block: RenderBlock): string {
  if (block.kind === 'table' || block.kind === 'divider') return '';
  return block.children
    .filter((c): c is Extract<RenderInlineNode, { kind: 'text' }> => c.kind === 'text')
    .map((c) => c.text)
    .join(' ')
    .trim();
}

/** Draft summary counts for the export summary line. */
export function draftEntryCount(draft: ReviewDraft): number {
  return draft.entries.length;
}

export type { DraftEntry };

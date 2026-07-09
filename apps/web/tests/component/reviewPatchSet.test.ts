import { describe, it, expect } from 'vitest';
import {
  blockPlainText,
  buildPatchFilename,
  buildPatchSet,
  collectExportErrors,
  firstEditableText,
  isBlockIndexInBounds,
} from '../../src/lib/review/patchSet';
import { buildTextOp } from '../../src/lib/review/operations';
import { validateAgainstSchema } from '../../src/lib/review/schemaValidate';
import { normalizeRenderPage } from '../../src/lib/render/normalize';
import type { ReviewDraft } from '../../src/lib/review/draft';
import fixture from '../../public/documents/review_sample/en/data/render_page.p0001.json';
import patchSchema from '../../../../packages/schemas/jsonschema/patch_set_v1.schema.json';

const page = normalizeRenderPage(fixture);
const NOW = new Date('2026-07-09T12:00:00.000Z');

function draftWith(entries: ReviewDraft['entries'], author = 'reviewer'): ReviewDraft {
  return { author, entries };
}

function textEntry(blockIndex = 1) {
  return {
    id: 'text-1',
    scope: 'text' as const,
    blockRef: page.blocks[blockIndex]?.id ?? 'missing',
    blockIndex,
    reason: 'fix casing',
    summary: 'Text: "…" → "…"',
    operation: buildTextOp(blockIndex, 0, "Roll dice equal to the titan's ATTACK value."),
  };
}

describe('buildPatchSet', () => {
  it('produces a schema-valid patch_set.v1 with render_page target + provenance', () => {
    const built = buildPatchSet({
      documentId: 'review_sample',
      edition: 'en',
      pageId: 'p0001',
      draft: draftWith([textEntry()]),
      sourceConfidence: null,
      now: NOW,
    });
    expect(built.schema_version).toBe('patch_set.v1');
    expect(built.target_kind).toBe('render_page');
    expect(built.operations).toHaveLength(1);
    expect(built.author).toBe('reviewer');
    expect(built.provenance?.author).toBe('reviewer');
    expect(built.provenance?.created_at).toBe(NOW.toISOString());
    expect(built.reason).toBe('fix casing');

    // Acceptance #4: the export validates against the committed JSON Schema.
    const errors = validateAgainstSchema(built, patchSchema);
    expect(errors).toEqual([]);
  });

  it('joins per-correction reasons into the set-level reason', () => {
    const built = buildPatchSet({
      documentId: 'd',
      edition: 'en',
      pageId: 'p0001',
      draft: draftWith([
        { ...textEntry(1), id: 'a', reason: 'reason A' },
        { ...textEntry(2), id: 'b', reason: 'reason B' },
      ]),
      now: NOW,
    });
    expect(built.reason).toBe('reason A; reason B');
  });

  it('builds the download filename with colons/dots sanitized', () => {
    const name = buildPatchFilename({
      documentId: 'review_sample',
      edition: 'en',
      pageId: 'p0001',
      draft: draftWith([]),
      now: NOW,
    });
    expect(name).toBe('patch-review_sample-en-p0001-2026-07-09T12-00-00-000Z.json');
  });
});

describe('export guards (collectExportErrors)', () => {
  it('passes a well-formed draft', () => {
    expect(collectExportErrors(draftWith([textEntry()]), page)).toEqual([]);
  });

  it('rejects an empty operation list', () => {
    const errors = collectExportErrors(draftWith([]), page);
    expect(errors.join(' ')).toContain('at least one correction');
  });

  it('rejects a missing author', () => {
    const errors = collectExportErrors(draftWith([textEntry()], ''), page);
    expect(errors.join(' ')).toContain('Author is required');
  });

  it('rejects an out-of-bounds block index', () => {
    const bad = { ...textEntry(1), blockIndex: 99 };
    const errors = collectExportErrors(draftWith([bad]), page);
    expect(errors.join(' ')).toContain('out of range');
  });

  it('rejects a correction with an empty reason', () => {
    const bad = { ...textEntry(1), reason: '   ' };
    const errors = collectExportErrors(draftWith([bad]), page);
    expect(errors.join(' ')).toContain('missing a reason');
  });
});

describe('isBlockIndexInBounds', () => {
  it('accepts in-range and rejects out-of-range / non-integer', () => {
    expect(isBlockIndexInBounds(0, page)).toBe(true);
    expect(isBlockIndexInBounds(3, page)).toBe(true);
    expect(isBlockIndexInBounds(4, page)).toBe(false);
    expect(isBlockIndexInBounds(-1, page)).toBe(false);
    expect(isBlockIndexInBounds(1.5, page)).toBe(false);
  });
});

describe('block text helpers', () => {
  it('firstEditableText returns the first text inline of a non-table block', () => {
    const t = firstEditableText(page.blocks[1]);
    expect(t).not.toBeNull();
    expect(t?.inlineIndex).toBe(0);
    expect(t?.text).toBe("Roll dice equal to the titan's Attack value.");
  });

  it('blockPlainText concatenates the visible text', () => {
    expect(blockPlainText(page.blocks[0])).toBe('Attack Phase');
  });
});

describe('schema validator (three-input discipline)', () => {
  it('flags a missing required patch_id', () => {
    const errors = validateAgainstSchema({ schema_version: 'patch_set.v1' }, patchSchema);
    expect(errors.some((e) => e.path.endsWith('patch_id'))).toBe(true);
  });

  it('flags an invalid scope enum value', () => {
    const bad = {
      patch_id: 'x',
      operations: [{ op: 'replace', path: '/blocks/0', scope: 'not_a_scope' }],
    };
    const errors = validateAgainstSchema(bad, patchSchema);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('flags a schema_version that violates the pattern', () => {
    const bad = { patch_id: 'x', schema_version: 'patch_set.vX' };
    const errors = validateAgainstSchema(bad, patchSchema);
    expect(errors.some((e) => e.message.includes('pattern'))).toBe(true);
  });
});

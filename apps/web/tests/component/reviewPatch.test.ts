import Ajv from 'ajv';
import { beforeEach, describe, expect, it } from 'vitest';
import patchSetSchema from '../../../../packages/schemas/jsonschema/patch_set_v1.schema.json';
import renderFixture from '../../public/documents/extraction_review/en/data/render_page.p0001.json';
import { normalizeRenderPage } from '../../src/lib/render/normalize';
import {
  buildPatchFilename,
  buildPatchSet,
  buildReadingOrderOperation,
  buildSuppressOperation,
  buildTextOperation,
  resolvePointer,
} from '../../src/lib/review/patches';
import {
  loadReviewDraft,
  reviewStorageKey,
  saveReviewDraft,
} from '../../src/lib/review/persistence';

const page = normalizeRenderPage(renderFixture);

describe('review patch operations', () => {
  it('builds a text pointer that resolves to the selected inline', () => {
    const operation = buildTextOperation(page.blocks, 1, 0, 'Move up to two spaces.');

    expect(operation).toEqual({
      op: 'replace',
      path: '/blocks/1/children/0/text',
      value: 'Move up to two spaces.',
      scope: 'text',
    });
    expect(resolvePointer(renderFixture, operation.path)).toBe('Move up to tree spaces.');
  });

  it('rejects out-of-bounds block and inline indices', () => {
    expect(() => buildTextOperation(page.blocks, -1, 0, 'x')).toThrow(/block index/i);
    expect(() => buildTextOperation(page.blocks, page.blocks.length, 0, 'x')).toThrow(
      /block index/i,
    );
    expect(() => buildTextOperation(page.blocks, 1, 3, 'x')).toThrow(/inline index/i);
  });

  it('moves a block earlier with a typed blocks-array replacement', () => {
    const operation = buildReadingOrderOperation(page.blocks, 1, 'earlier');

    expect(operation.op).toBe('replace');
    expect(operation.path).toBe('/blocks');
    expect(operation.scope).toBe('reading_order');
    expect(Array.isArray(operation.value)).toBe(true);
    const reordered = operation.value as Array<{ id: string }>;
    expect(reordered.map((block) => block.id)).toEqual(['p0001.b002', 'p0001.b001', 'p0001.b003']);
  });

  it('refuses reading-order moves beyond the page boundaries', () => {
    expect(() => buildReadingOrderOperation(page.blocks, 0, 'earlier')).toThrow(/already first/i);
    expect(() => buildReadingOrderOperation(page.blocks, page.blocks.length - 1, 'later')).toThrow(
      /already last/i,
    );
  });

  it('builds a block-structure suppression operation', () => {
    expect(buildSuppressOperation(page.blocks, 2)).toEqual({
      op: 'delete',
      path: '/blocks/2',
      scope: 'block_structure',
    });
  });
});

describe('review patch export', () => {
  const operation = () => buildTextOperation(page.blocks, 1, 0, 'Move up to two spaces.');
  const createdAt = new Date('2026-07-10T00:00:00.000Z');

  it('builds the generated PatchSetV1 export shape and filename', () => {
    const patchSet = buildPatchSet(
      'extraction_review',
      'en',
      'p0001',
      [operation()],
      ' Correct OCR typo ',
      ' reviewer@example.com ',
      0.82,
      createdAt,
    );

    expect(patchSet).toEqual({
      schema_version: 'patch_set.v1',
      patch_id: 'patch-extraction_review-en-p0001-2026-07-10T00-00-00-000Z',
      target_artifact_ref: 'documents/extraction_review/en/data/render_page.p0001.json',
      target_kind: 'render_page',
      operations: [operation()],
      reason: 'Correct OCR typo',
      author: 'reviewer@example.com',
      provenance: {
        author: 'reviewer@example.com',
        created_at: '2026-07-10T00:00:00.000Z',
        source_confidence: 0.82,
      },
    });
    expect(buildPatchFilename(patchSet)).toBe(
      'patch-extraction_review-en-p0001-2026-07-10T00-00-00-000Z.json',
    );
  });

  it('validates the exact export against the generated JSON Schema', () => {
    const validate = new Ajv({ strict: false, formats: { 'date-time': true } }).compile(
      patchSetSchema,
    );
    const patchSet = buildPatchSet(
      'extraction_review',
      'en',
      'p0001',
      [operation()],
      'Correct OCR typo',
      'reviewer@example.com',
      0.82,
      createdAt,
    );

    expect(validate(patchSet), JSON.stringify(validate.errors)).toBe(true);
  });

  it('blocks export without operations, reason, or author', () => {
    expect(() =>
      buildPatchSet('doc', 'en', 'p0001', [], 'reason', 'author', null, createdAt),
    ).toThrow(/operation/i);
    expect(() =>
      buildPatchSet('doc', 'en', 'p0001', [operation()], ' ', 'author', null, createdAt),
    ).toThrow(/reason/i);
    expect(() =>
      buildPatchSet('doc', 'en', 'p0001', [operation()], 'reason', ' ', null, createdAt),
    ).toThrow(/author/i);
  });
});

describe('review draft persistence', () => {
  const key = () => reviewStorageKey('extraction_review', 'en', 'p0001');

  beforeEach(() => localStorage.clear());

  it('restores operations, reason, and author for the same page', () => {
    const operations = [buildTextOperation(page.blocks, 1, 0, 'Corrected')];
    saveReviewDraft(key(), { operations, reason: 'OCR typo', author: 'reviewer' });

    expect(loadReviewDraft(key())).toEqual({
      operations,
      reason: 'OCR typo',
      author: 'reviewer',
    });
    expect(reviewStorageKey('extraction_review', 'en', 'p0002')).not.toBe(key());
  });

  it('fails closed when persisted JSON is malformed', () => {
    localStorage.setItem(key(), '{broken');
    expect(loadReviewDraft(key())).toEqual({ operations: [], reason: '', author: '' });

    localStorage.setItem(
      key(),
      JSON.stringify({
        operations: [{ op: 'replace', path: '/blocks/0', scope: 'untyped_scope' }],
        reason: 'bad draft',
        author: 'reviewer',
      }),
    );
    expect(loadReviewDraft(key())).toEqual({ operations: [], reason: '', author: '' });
  });
});

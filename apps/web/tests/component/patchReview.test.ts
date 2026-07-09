import { describe, expect, it } from 'vitest';
import type { PatchSetV1 } from '@atr/schemas';
import patchSchema from '../../../../packages/schemas/jsonschema/patch_set_v1.schema.json';
import type { RenderPageData } from '../../src/lib/render/types';
import {
  buildBlockPath,
  buildPatchFilename,
  buildPatchSet,
  buildReadingOrderOperations,
  buildSuppressBlockOperation,
  buildTextCorrectionOperation,
  resolveJsonPointer,
} from '../../src/lib/patch-review/export';

const page: RenderPageData = {
  schema_version: 'render_page.v1',
  document_version: '',
  presentation_mode: 'article',
  page: {
    id: 'p0001',
    title: 'Review Fixture',
    section_path: [],
    source_page_number: 1,
  },
  nav: {
    prev: null,
    next: null,
    parent_section: '',
  },
  blocks: [
    {
      kind: 'heading',
      id: 'p0001.b001',
      level: 2,
      children: [{ kind: 'text', text: 'Original heading', marks: [] }],
    },
    {
      kind: 'paragraph',
      id: 'p0001.b002',
      children: [{ kind: 'text', text: 'Original body', marks: ['bold'] }],
    },
    {
      kind: 'paragraph',
      id: 'p0001.b003',
      children: [{ kind: 'text', text: 'Later body', marks: [] }],
    },
  ],
  figures: {},
  facsimile: null,
  glossary_mentions: [],
  source_map: {
    document_id: 'review_fixture',
    page_id: 'p0001',
    block_refs: ['p0001.b001', 'p0001.b002', 'p0001.b003'],
  },
  build_meta: {
    build_id: 'fixture-build',
    generated_at: '2026-07-09T08:00:00.000Z',
  },
  search: {},
};

describe('patch review helpers', () => {
  it('builds escaped JSON Pointer paths into blocks', () => {
    expect(buildBlockPath(2, 'children', 0, 'text')).toBe('/blocks/2/children/0/text');
    expect(buildBlockPath(0, 'metadata/a~b')).toBe('/blocks/0/metadata~1a~0b');
  });

  it('rejects out-of-bounds block indices', () => {
    expect(() => buildTextCorrectionOperation(page, 99, 'Fixed')).toThrow(/out of bounds/);
    expect(() => buildSuppressBlockOperation(page, -1)).toThrow(/out of bounds/);
  });

  it('drafts a text correction operation whose pointer resolves in the render page', () => {
    const op = buildTextCorrectionOperation(page, 1, 'Corrected body');

    expect(op).toEqual({
      op: 'replace',
      path: '/blocks/1/children/0',
      value: { kind: 'text', text: 'Corrected body', marks: ['bold'] },
      scope: 'text',
    });
    expect(resolveJsonPointer(page, op.path)).toEqual({
      kind: 'text',
      text: 'Original body',
      marks: ['bold'],
    });
  });

  it('drafts reading-order operations by deleting and inserting a block object', () => {
    const ops = buildReadingOrderOperations(page, 1, 'later');

    expect(ops).toEqual([
      { op: 'delete', path: '/blocks/1', scope: 'reading_order' },
      {
        op: 'insert',
        path: '/blocks/2',
        value: page.blocks[1],
        scope: 'reading_order',
      },
    ]);
    expect(resolveJsonPointer(page, ops[0].path)).toBe(page.blocks[1]);
  });

  it('blocks reading-order moves beyond page bounds', () => {
    expect(() => buildReadingOrderOperations(page, 0, 'earlier')).toThrow(/Cannot move/);
    expect(() => buildReadingOrderOperations(page, 2, 'later')).toThrow(/Cannot move/);
  });

  it('drafts a block suppression operation', () => {
    expect(buildSuppressBlockOperation(page, 2)).toEqual({
      op: 'delete',
      path: '/blocks/2',
      scope: 'block_structure',
    });
  });

  it('requires author, reason, and at least one operation before export', () => {
    const now = new Date('2026-07-09T09:10:11.000Z');
    expect(() =>
      buildPatchSet({
        documentId: 'review_fixture',
        edition: 'en',
        pageId: 'p0001',
        page,
        operations: [],
        author: 'Reviewer',
        reason: 'Correct extraction',
        now,
      }),
    ).toThrow(/operation/);

    expect(() =>
      buildPatchSet({
        documentId: 'review_fixture',
        edition: 'en',
        pageId: 'p0001',
        page,
        operations: [buildSuppressBlockOperation(page, 2)],
        author: ' ',
        reason: 'Correct extraction',
        now,
      }),
    ).toThrow(/author/);

    expect(() =>
      buildPatchSet({
        documentId: 'review_fixture',
        edition: 'en',
        pageId: 'p0001',
        page,
        operations: [buildSuppressBlockOperation(page, 2)],
        author: 'Reviewer',
        reason: ' ',
        now,
      }),
    ).toThrow(/reason/);
  });

  it('builds a generated PatchSetV1 shape and schema-valid enum values', () => {
    const now = new Date('2026-07-09T09:10:11.000Z');
    const patchSet: PatchSetV1 = buildPatchSet({
      documentId: 'review_fixture',
      edition: 'en',
      pageId: 'p0001',
      page,
      operations: [buildTextCorrectionOperation(page, 1, 'Corrected body')],
      author: 'Reviewer',
      reason: 'Correct extraction text',
      sourceConfidence: 0.82,
      now,
    });

    expect(patchSet).toEqual({
      schema_version: 'patch_set.v1',
      patch_id: 'patch-review_fixture-en-p0001-2026-07-09T09-10-11-000Z',
      target_artifact_ref: 'documents/review_fixture/en/data/render_page.p0001.json',
      target_kind: 'render_page',
      operations: [
        {
          op: 'replace',
          path: '/blocks/1/children/0',
          value: { kind: 'text', text: 'Corrected body', marks: ['bold'] },
          scope: 'text',
        },
      ],
      reason: 'Correct extraction text',
      author: 'Reviewer',
      provenance: {
        author: 'Reviewer',
        created_at: '2026-07-09T09:10:11.000Z',
        source_confidence: 0.82,
        expected_confidence_delta: null,
      },
    });
    expect(patchSchema.$defs.PatchScope.enum).toContain(patchSet.operations?.[0]?.scope);
    expect(patchSchema.$defs.PatchTargetKind.enum).toContain(patchSet.target_kind);
    expect(patchSchema.required).toContain('patch_id');
  });

  it('builds a stable download filename', () => {
    const now = new Date('2026-07-09T09:10:11.000Z');
    const patchSet = buildPatchSet({
      documentId: 'review_fixture',
      edition: 'en',
      pageId: 'p0001',
      page,
      operations: [buildSuppressBlockOperation(page, 2)],
      author: 'Reviewer',
      reason: 'Suppress duplicate block',
      now,
    });

    expect(buildPatchFilename(patchSet, 'review_fixture', 'en', 'p0001')).toBe(
      'patch-review_fixture-en-p0001-2026-07-09T09-10-11-000Z.json',
    );
  });
});

import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { InvalidRenderPageError, normalizeRenderPage } from '../../src/lib/render/normalize';

describe('normalizeRenderPage — structural validation', () => {
  it('rejects non-object payloads', () => {
    expect(() => normalizeRenderPage('nope')).toThrow(InvalidRenderPageError);
    expect(() => normalizeRenderPage(null)).toThrow(InvalidRenderPageError);
    expect(() => normalizeRenderPage([])).toThrow(InvalidRenderPageError);
  });

  it('rejects unsupported schema_version', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v2',
        page: { id: 'p0001' },
      }),
    ).toThrow(/unsupported "render_page\.v2"/);
  });

  it('accepts missing schema_version and defaults it', () => {
    const out = normalizeRenderPage({ page: { id: 'p0001' } });
    expect(out.schema_version).toBe('render_page.v1');
  });

  it('rejects payload missing page.id', () => {
    expect(() => normalizeRenderPage({ schema_version: 'render_page.v1', page: {} })).toThrow(
      /page\.id: missing required string/,
    );
  });

  it('rejects an unknown block kind with the offending path', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v1',
        page: { id: 'p0001' },
        blocks: [{ kind: 'mystery', id: 'p0001.b001' }],
      }),
    ).toThrow(/blocks\[0\]\.kind: unsupported block kind "mystery"/);
  });

  it('rejects an unknown inline kind with the offending path', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v1',
        page: { id: 'p0001' },
        blocks: [
          {
            kind: 'paragraph',
            id: 'p0001.b001',
            children: [{ kind: 'hologram', text: '…' }],
          },
        ],
      }),
    ).toThrow(/blocks\[0\]\.children\[0\]\.kind: unsupported inline kind "hologram"/);
  });

  it('rejects a block missing its kind discriminator', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v1',
        page: { id: 'p0001' },
        blocks: [{ id: 'p0001.b001' }],
      }),
    ).toThrow(/blocks\[0\]\.kind: missing required string/);
  });

  it('normalizes table rows and cells (S5U-704)', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0054' },
      blocks: [
        {
          kind: 'table',
          id: 'p0054.b002',
          children: [
            {
              kind: 'table_row',
              id: 'p0054.b002.r0',
              header: true,
              cells: [
                {
                  kind: 'table_cell',
                  id: 'p0054.b002.r0.c0',
                  header: true,
                  children: [{ kind: 'text', text: 'BP I' }],
                },
                {
                  kind: 'table_cell',
                  id: 'p0054.b002.r0.c1',
                  children: [{ kind: 'text', text: 'AI deck' }],
                },
              ],
            },
          ],
        },
      ],
    });
    const block = out.blocks[0];
    expect(block.kind).toBe('table');
    if (block.kind === 'table') {
      expect(block.children).toHaveLength(1);
      const row = block.children[0];
      expect(row.kind).toBe('table_row');
      if (row.kind === 'table_row') {
        expect(row.header).toBe(true);
        expect(row.cells).toHaveLength(2);
        expect(row.cells[0].header).toBe(true);
        expect(row.cells[0].children[0]).toEqual({
          kind: 'text',
          text: 'BP I',
          marks: [],
        });
      }
    }
  });

  it('preserves legacy flat table children (back-compat)', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0054' },
      blocks: [
        {
          kind: 'table',
          id: 'p0054.b002',
          children: [
            { kind: 'text', text: 'BP I' },
            { kind: 'text', text: '\n' },
            { kind: 'text', text: 'AI deck' },
          ],
        },
      ],
    });
    const block = out.blocks[0];
    expect(block.kind).toBe('table');
    if (block.kind === 'table') {
      expect(block.children).toHaveLength(3);
      expect(block.children.every((c) => c.kind === 'text')).toBe(true);
    }
  });

  it('rejects an unknown table child kind', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v1',
        page: { id: 'p0054' },
        blocks: [
          {
            kind: 'table',
            id: 'p0054.b002',
            children: [{ kind: 'mystery_cell' }],
          },
        ],
      }),
    ).toThrow(/blocks\[0\]\.children\[0\]\.kind: unsupported inline kind "mystery_cell"/);
  });

  it('rejects a table_row with no cells array missing its kind tag', () => {
    expect(() =>
      normalizeRenderPage({
        schema_version: 'render_page.v1',
        page: { id: 'p0054' },
        blocks: [
          {
            kind: 'table',
            id: 'p0054.b002',
            children: [{ kind: 'table_row', id: 'r0', cells: [{ id: 'c0' }] }],
          },
        ],
      }),
    ).toThrow(/blocks\[0\]\.children\[0\]\.cells\[0\]\.kind: missing required string/);
  });
});

describe('normalizeRenderPage — defaulted-field materialization', () => {
  it('materializes blocks, children, nav, figures, search, source_map, build_meta', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
    });
    expect(out.blocks).toEqual([]);
    expect(out.nav).toEqual({ prev: null, next: null, parent_section: '' });
    expect(out.figures).toEqual({});
    expect(out.glossary_mentions).toEqual([]);
    expect(out.source_map).toBeNull();
    expect(out.build_meta).toBeNull();
    expect(out.facsimile).toBeNull();
    expect(out.search).toEqual({});
    expect(out.presentation_mode).toBe('article');
    expect(out.document_version).toBe('');
  });

  it('materializes heading level default and paragraph children default', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
      blocks: [
        { kind: 'heading', id: 'p0001.b001' },
        { kind: 'paragraph', id: 'p0001.b002' },
      ],
    });
    expect(out.blocks).toHaveLength(2);
    const heading = out.blocks[0];
    expect(heading.kind).toBe('heading');
    if (heading.kind === 'heading') {
      expect(heading.level).toBe(1);
      expect(heading.children).toEqual([]);
    }
    const paragraph = out.blocks[1];
    if (paragraph.kind === 'paragraph') {
      expect(paragraph.children).toEqual([]);
    }
  });

  it('materializes defaulted page.source_page_number to 0', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
    });
    expect(out.page.source_page_number).toBe(0);
    expect(out.page.section_path).toEqual([]);
    expect(out.page.title).toBe('');
  });

  it('materializes inline marks and icon alt defaults', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
      blocks: [
        {
          kind: 'paragraph',
          id: 'p0001.b001',
          children: [
            { kind: 'text', text: 'hello' },
            { kind: 'icon', symbol_id: 'sym.progress' },
            { kind: 'figure_ref', asset_id: 'fig1' },
          ],
        },
      ],
    });
    const children = out.blocks[0].kind === 'paragraph' ? out.blocks[0].children : [];
    expect(children[0]).toEqual({ kind: 'text', text: 'hello', marks: [] });
    expect(children[1]).toEqual({ kind: 'icon', symbol_id: 'sym.progress', alt: '' });
    expect(children[2]).toEqual({ kind: 'figure_ref', asset_id: 'fig1', label: '' });
  });

  it('preserves facsimile, search, and source_map when present', () => {
    const out = normalizeRenderPage({
      schema_version: 'render_page.v1',
      presentation_mode: 'facsimile',
      page: { id: 'p0001' },
      facsimile: {
        raster_src: '/r.png',
        annotations: [{ text: 'A', bbox: { x0: 0, y0: 0, x1: 1, y1: 1 } }],
      },
      search: { raw_text: 'abc', normalized_terms: ['a', 'b'] },
      source_map: { page_id: 'p0001' },
      build_meta: { build_id: 'b1' },
    });
    expect(out.presentation_mode).toBe('facsimile');
    expect(out.facsimile?.raster_src).toBe('/r.png');
    expect(out.facsimile?.annotations[0].kind).toBe('body');
    expect(out.facsimile?.annotations[0].priority).toBe(0);
    expect(out.search.raw_text).toBe('abc');
    expect(out.search.normalized_terms).toEqual(['a', 'b']);
    expect(out.source_map).toEqual({ page_id: 'p0001', block_refs: [] });
    expect(out.build_meta).toEqual({ build_id: 'b1', generated_at: '' });
  });
});

describe('normalizeRenderPage — committed bundles must load', () => {
  const publicDocs = path.resolve(__dirname, '../../public/documents');

  function findRenderPageFiles(dir: string): string[] {
    const out: string[] = [];
    if (!fs.existsSync(dir)) return out;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        out.push(...findRenderPageFiles(full));
      } else if (entry.isFile() && /^render_page\..*\.json$/.test(entry.name)) {
        out.push(full);
      }
    }
    return out;
  }

  const files = findRenderPageFiles(publicDocs);

  it('discovers at least one committed bundle to validate', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files.map((f) => [path.relative(publicDocs, f), f]))(
    'normalizes %s without throwing',
    (_rel, file) => {
      const raw = JSON.parse(fs.readFileSync(file as string, 'utf-8'));
      const normalized = normalizeRenderPage(raw);
      expect(normalized.schema_version).toBe('render_page.v1');
      expect(normalized.page.id).toBeTruthy();
    },
  );
});

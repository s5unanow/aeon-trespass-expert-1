import { cleanup, render, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TableBlock } from '../../src/components/reader/TableBlock';
import type {
  RenderTableBlock,
  RenderTableCellBlock,
  RenderTableRowBlock,
} from '../../src/lib/render/types';

afterEach(() => {
  cleanup();
});

function makeCell(
  id: string,
  text: string,
  header = false,
): RenderTableCellBlock {
  return {
    kind: 'table_cell',
    id,
    header,
    children: [{ kind: 'text', text, marks: [] }],
  };
}

function makeRow(id: string, cells: RenderTableCellBlock[], header = false): RenderTableRowBlock {
  return { kind: 'table_row', id, header, cells };
}

describe('TableBlock', () => {
  it('renders structured rows and cells as <table><tbody><tr><td> (S5U-704)', () => {
    const block: RenderTableBlock = {
      kind: 'table',
      id: 'p0054.b002',
      children: [
        makeRow('p0054.b002.r0', [
          makeCell('p0054.b002.r0.c0', 'BP I', true),
          makeCell('p0054.b002.r0.c1', 'Action A', true),
          makeCell('p0054.b002.r0.c2', 'Action B', true),
        ], true),
        makeRow('p0054.b002.r1', [
          makeCell('p0054.b002.r1.c0', 'BP II'),
          makeCell('p0054.b002.r1.c1', 'Shuffle a BP III card'),
          makeCell('p0054.b002.r1.c2', 'Search AI discard pile'),
        ]),
      ],
    };
    const { container } = render(<TableBlock block={block} />);
    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    const rows = within(table as HTMLElement).getAllByRole('row');
    expect(rows).toHaveLength(2);
    const headerCells = within(rows[0]).getAllByRole('columnheader');
    expect(headerCells).toHaveLength(3);
    expect(headerCells[0].textContent).toBe('BP I');
    const bodyCells = within(rows[1]).getAllByRole('cell');
    expect(bodyCells).toHaveLength(3);
    expect(bodyCells[0].textContent).toBe('BP II');
    expect(bodyCells[1].textContent).toContain('BP III');
  });

  it('renders legacy flat inline children as <div> pre-wrap (back-compat)', () => {
    const block: RenderTableBlock = {
      kind: 'table',
      id: 'p0054.b003',
      children: [
        { kind: 'text', text: 'BP I  ', marks: [] },
        { kind: 'text', text: '\n', marks: [] },
        { kind: 'text', text: 'Shuffle a BP II card', marks: [] },
      ],
    };
    const { container } = render(<TableBlock block={block} />);
    const div = container.querySelector('div.reader-table');
    expect(div).not.toBeNull();
    expect(container.querySelector('table')).toBeNull();
    expect(div?.textContent).toContain('BP I');
    expect(div?.textContent).toContain('Shuffle');
  });

  it('prefers structured rendering when child list mixes rows and stray inlines', () => {
    const block: RenderTableBlock = {
      kind: 'table',
      id: 'p0099.b001',
      children: [
        { kind: 'text', text: 'stray', marks: [] },
        makeRow('r0', [makeCell('c0', 'A'), makeCell('c1', 'B')]),
      ],
    };
    const { container } = render(<TableBlock block={block} />);
    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    // Stray inlines are dropped when rows are present.
    expect(table?.textContent).not.toContain('stray');
    expect(table?.textContent).toContain('A');
  });
});

import type {
  RenderTableBlock as TableData,
  RenderTableCellBlock,
  RenderTableRowBlock,
} from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface TableBlockProps {
  block: TableData;
}

function isRow(
  child: TableData['children'][number],
): child is RenderTableRowBlock {
  return (child as { kind: string }).kind === 'table_row';
}

function Cell({ cell }: { cell: RenderTableCellBlock }) {
  const Tag = cell.header ? 'th' : 'td';
  return (
    <Tag id={cell.id} className="reader-table-cell" scope={cell.header ? 'col' : undefined}>
      {cell.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </Tag>
  );
}

function Row({ row }: { row: RenderTableRowBlock }) {
  return (
    <tr id={row.id} className={row.header ? 'reader-table-row reader-table-row-header' : 'reader-table-row'}>
      {row.cells.map((cell) => (
        <Cell key={cell.id} cell={cell} />
      ))}
    </tr>
  );
}

export function TableBlock({ block }: TableBlockProps) {
  // S5U-704 — structured tables render as <table><tbody><tr><td>; legacy
  // flat-inline tables fall through to the pre-wrap div for back-compat
  // with cached artifacts that predate the row/cell schema.
  const rowChildren = block.children.filter(isRow);
  const hasRows = rowChildren.length > 0;

  if (hasRows) {
    return (
      <table id={block.id} className="reader-table reader-table-structured">
        <tbody>
          {rowChildren.map((row) => (
            <Row key={row.id} row={row} />
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div id={block.id} className="reader-table" role="table">
      {block.children.map((child, i) => {
        if (isRow(child)) {
          return null;
        }
        return <InlineRenderer key={i} node={child} />;
      })}
    </div>
  );
}

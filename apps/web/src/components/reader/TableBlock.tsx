import type { RenderTableBlock as TableData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface TableBlockProps {
  block: TableData;
}

export function TableBlock({ block }: TableBlockProps) {
  return (
    <div id={block.id} className="reader-table" role="table">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </div>
  );
}

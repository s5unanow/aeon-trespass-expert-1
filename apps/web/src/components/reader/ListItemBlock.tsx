import type { RenderListItemBlock as ListItemData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface ListItemBlockProps {
  block: ListItemData;
}

export function ListItemBlock({ block }: ListItemBlockProps) {
  return (
    <li id={block.id} className="reader-list-item">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </li>
  );
}

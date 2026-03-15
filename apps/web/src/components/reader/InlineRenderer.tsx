import type { RenderInlineNode } from '../../lib/render/types';
import { IconInline } from './IconInline';

interface InlineRendererProps {
  node: RenderInlineNode;
}

export function InlineRenderer({ node }: InlineRendererProps) {
  switch (node.kind) {
    case 'text':
      return <span>{node.text}</span>;
    case 'icon':
      return <IconInline symbolId={node.symbol_id} alt={node.alt} />;
    case 'figure_ref':
      return (
        <a href={`#${node.asset_id}`} className="figure-ref">
          {node.label || 'Figure'}
        </a>
      );
    default:
      return null;
  }
}

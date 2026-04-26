import type { RenderInlineNode } from '../../lib/render/types';
import { GlossaryText } from './GlossaryText';
import { IconInline } from './IconInline';

interface InlineRendererProps {
  node: RenderInlineNode;
}

export function InlineRenderer({ node }: InlineRendererProps) {
  switch (node.kind) {
    case 'text':
      return <GlossaryText text={node.text} marks={node.marks} />;
    case 'icon':
      return <IconInline symbolId={node.symbol_id} alt={node.alt} />;
    case 'figure_ref':
      return (
        <a href={`#${node.asset_id}`} className="figure-ref">
          {node.label || 'Figure'}
        </a>
      );
    default: {
      const _exhaustive: never = node;
      throw new Error(`Unsupported inline kind: ${(_exhaustive as RenderInlineNode).kind}`);
    }
  }
}

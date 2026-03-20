import type { ReactNode } from 'react';
import type { RenderInlineNode } from '../../lib/render/types';
import { IconInline } from './IconInline';

interface InlineRendererProps {
  node: RenderInlineNode;
}

function wrapMarks(text: string, marks?: string[]): ReactNode {
  let result: ReactNode = text;
  if (marks?.includes('bold')) {
    result = <strong>{result}</strong>;
  }
  if (marks?.includes('italic')) {
    result = <em>{result}</em>;
  }
  return result;
}

export function InlineRenderer({ node }: InlineRendererProps) {
  switch (node.kind) {
    case 'text':
      return <span>{wrapMarks(node.text, node.marks)}</span>;
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
      throw new Error(
        `Unsupported inline kind: ${(_exhaustive as RenderInlineNode).kind}`,
      );
    }
  }
}

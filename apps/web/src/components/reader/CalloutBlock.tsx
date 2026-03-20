import type { RenderCalloutBlock as CalloutData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface CalloutBlockProps {
  block: CalloutData;
}

export function CalloutBlock({ block }: CalloutBlockProps) {
  return (
    <aside id={block.id} className="reader-callout" data-variant={block.variant ?? undefined}>
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </aside>
  );
}

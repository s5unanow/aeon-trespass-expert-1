import type { RenderParagraphBlock as ParagraphData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface ParagraphBlockProps {
  block: ParagraphData;
}

export function ParagraphBlock({ block }: ParagraphBlockProps) {
  return (
    <p id={block.id} className="reader-paragraph">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </p>
  );
}

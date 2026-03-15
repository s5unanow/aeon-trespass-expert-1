import type { RenderFigureBlock as FigureData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface FigureBlockProps {
  block: FigureData;
}

export function FigureBlock({ block }: FigureBlockProps) {
  return (
    <figure id={block.id} className="reader-figure">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </figure>
  );
}

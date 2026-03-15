import type { RenderBlock } from '../../lib/render/types';
import { HeadingBlock } from './HeadingBlock';
import { ParagraphBlock } from './ParagraphBlock';
import { FigureBlock } from './FigureBlock';

interface BlockRendererProps {
  block: RenderBlock;
}

export function BlockRenderer({ block }: BlockRendererProps) {
  switch (block.kind) {
    case 'heading':
      return <HeadingBlock block={block} />;
    case 'paragraph':
      return <ParagraphBlock block={block} />;
    case 'figure':
      return <FigureBlock block={block} />;
    case 'divider':
      return <hr id={block.id} className="reader-divider" />;
    default:
      return null;
  }
}

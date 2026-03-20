import type { RenderParagraphBlock as ParagraphData } from '../../lib/render/types';
import { parseTocEntries } from '../../lib/render/toc';
import { InlineRenderer } from './InlineRenderer';
import { TocBlock } from './TocBlock';

interface ParagraphBlockProps {
  block: ParagraphData;
}

export function ParagraphBlock({ block }: ParagraphBlockProps) {
  const tocEntries = parseTocEntries(block.children);
  if (tocEntries) {
    return <TocBlock id={block.id} entries={tocEntries} />;
  }

  return (
    <p id={block.id} className="reader-paragraph">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </p>
  );
}

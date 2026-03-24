import type { RenderParagraphBlock as ParagraphData } from '../../lib/render/types';
import { parseTocEntries } from '../../lib/render/toc';
import { InlineRenderer } from './InlineRenderer';
import { TocBlock } from './TocBlock';

interface ParagraphBlockProps {
  block: ParagraphData;
  pageOffset?: number;
}

export function ParagraphBlock({ block, pageOffset }: ParagraphBlockProps) {
  const tocEntries = parseTocEntries(block.children);
  if (tocEntries) {
    return <TocBlock id={block.id} entries={tocEntries} pageOffset={pageOffset} />;
  }

  return (
    <p id={block.id} className="reader-paragraph">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </p>
  );
}

import { createElement } from 'react';
import type { RenderHeadingBlock as HeadingData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface HeadingBlockProps {
  block: HeadingData;
}

export function HeadingBlock({ block }: HeadingBlockProps) {
  const tag = `h${Math.min(block.level, 6)}`;
  return createElement(
    tag,
    { id: block.id, className: 'reader-heading' },
    ...block.children.map((child, i) => <InlineRenderer key={i} node={child} />),
  );
}

import { describe, it, expect } from 'vitest';
import {
  blockPointer,
  blockTextPointer,
  blocksPointer,
  parsePointer,
  resolvePointer,
} from '../../src/lib/review/pointer';
import fixture from '../../public/documents/review_sample/en/data/render_page.p0001.json';

describe('review pointer builders', () => {
  it('builds text / block / blocks pointers', () => {
    expect(blockTextPointer(1, 0)).toBe('/blocks/1/children/0/text');
    expect(blockPointer(3)).toBe('/blocks/3');
    expect(blocksPointer()).toBe('/blocks');
  });

  // Acceptance #3: a drafted text pointer must resolve in the render JSON.
  it('resolves a drafted text pointer against the render page', () => {
    const pointer = blockTextPointer(1, 0);
    expect(resolvePointer(fixture, pointer)).toBe(
      "Roll dice equal to the titan's Attack value.",
    );
  });

  it('resolves a block pointer to the block object', () => {
    const block = resolvePointer(fixture, blockPointer(0)) as { id: string };
    expect(block.id).toBe('p0001.b001');
  });

  it('resolves the blocks-array pointer to the full ordered list', () => {
    const blocks = resolvePointer(fixture, blocksPointer()) as unknown[];
    expect(blocks).toHaveLength(4);
  });

  it('throws when a pointer runs off the end of an array', () => {
    expect(() => resolvePointer(fixture, blockPointer(99))).toThrow();
  });

  it('throws when a pointer descends into a missing key', () => {
    expect(() => resolvePointer(fixture, '/blocks/0/nope')).toThrow();
  });

  it('parsePointer handles empty, escapes, and rejects non-rooted pointers', () => {
    expect(parsePointer('')).toEqual([]);
    expect(parsePointer('/a~1b/c~0d')).toEqual(['a/b', 'c~d']);
    expect(() => parsePointer('blocks/0')).toThrow();
  });
});

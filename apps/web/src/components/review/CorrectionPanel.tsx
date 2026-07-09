import { useEffect, useMemo, useState } from 'react';
import type { patchSetV1 } from '@atr/schemas';
import type { RenderBlock } from '../../lib/render/types';
import {
  buildReadingOrderOperation,
  buildSuppressOperation,
  buildTextOperation,
} from '../../lib/review/patches';

interface CorrectionPanelProps {
  blocks: RenderBlock[];
  selectedIndex: number;
  onAdd: (operation: patchSetV1.PatchOperation) => void;
}

export function CorrectionPanel({ blocks, selectedIndex, onAdd }: CorrectionPanelProps) {
  const block = blocks[selectedIndex];
  const textInlines = useMemo(() => {
    if (!block || !('children' in block) || !Array.isArray(block.children)) return [];
    return block.children
      .map((child, index) => ({ child, index }))
      .filter((entry) => entry.child.kind === 'text');
  }, [block]);
  const [scope, setScope] = useState<patchSetV1.PatchScope>('text');
  const [inlineIndex, setInlineIndex] = useState(0);
  const [correctedText, setCorrectedText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const first = textInlines[0];
    setInlineIndex(first?.index ?? 0);
    setCorrectedText(first && first.child.kind === 'text' ? first.child.text : '');
    setScope('text');
    setError(null);
  }, [block?.id, textInlines]);

  if (!block) return null;

  function add(operation: patchSetV1.PatchOperation) {
    onAdd(operation);
    setError(null);
  }

  return (
    <section className="review-correction-panel" aria-labelledby="review-correction-title">
      <h2 id="review-correction-title">Correct {block.id}</h2>
      <label>
        <span>Correction scope</span>
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value as patchSetV1.PatchScope)}
        >
          <option value="text">Text</option>
          <option value="reading_order">Reading order</option>
          <option value="block_structure">Block structure</option>
        </select>
      </label>

      {scope === 'text' && (
        <div className="review-correction-fields">
          {textInlines.length === 0 ? (
            <p>This block has no directly editable text inline.</p>
          ) : (
            <>
              {textInlines.length > 1 && (
                <label>
                  <span>Text inline</span>
                  <select
                    value={inlineIndex}
                    onChange={(event) => {
                      const nextIndex = Number(event.target.value);
                      setInlineIndex(nextIndex);
                      const next = textInlines.find((entry) => entry.index === nextIndex);
                      setCorrectedText(next && next.child.kind === 'text' ? next.child.text : '');
                    }}
                  >
                    {textInlines.map((entry) => (
                      <option key={entry.index} value={entry.index}>
                        Inline {entry.index + 1}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                <span>Corrected text</span>
                <textarea
                  rows={4}
                  value={correctedText}
                  onChange={(event) => setCorrectedText(event.target.value)}
                />
              </label>
              <button
                type="button"
                onClick={() => {
                  try {
                    add(buildTextOperation(blocks, selectedIndex, inlineIndex, correctedText));
                  } catch (caught) {
                    setError(
                      caught instanceof Error ? caught.message : 'Unable to draft correction',
                    );
                  }
                }}
              >
                Add text correction
              </button>
            </>
          )}
        </div>
      )}

      {scope === 'reading_order' && (
        <div className="review-order-actions">
          <button
            type="button"
            disabled={selectedIndex === 0}
            onClick={() => add(buildReadingOrderOperation(blocks, selectedIndex, 'earlier'))}
          >
            Move earlier
          </button>
          <button
            type="button"
            disabled={selectedIndex === blocks.length - 1}
            onClick={() => add(buildReadingOrderOperation(blocks, selectedIndex, 'later'))}
          >
            Move later
          </button>
        </div>
      )}

      {scope === 'block_structure' && (
        <button type="button" onClick={() => add(buildSuppressOperation(blocks, selectedIndex))}>
          Suppress block
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

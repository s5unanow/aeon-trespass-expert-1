import { useMemo, useState } from 'react';
import type { RenderBlock } from '../../lib/render/types';
import {
  buildReorderOp,
  buildSuppressOp,
  buildTextOp,
  type ReorderDirection,
  type ReviewScope,
} from '../../lib/review/operations';
import { firstEditableText } from '../../lib/review/patchSet';
import { nextEntryId, type DraftEntry } from '../../lib/review/draft';

interface CorrectionPanelProps {
  block: RenderBlock;
  blockIndex: number;
  blockCount: number;
  /** Raw artifact blocks — reorder patches permute these for a faithful value. */
  rawBlocks: unknown[];
  onAdd: (entry: DraftEntry) => void;
}

function truncate(s: string, max = 40): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

const SCOPE_LABELS: Record<ReviewScope, string> = {
  text: 'Text',
  reading_order: 'Reading order',
  block_structure: 'Suppress block',
};

/**
 * Correction editor for the selected block. Supports the three MVP scopes —
 * `text` (edit the first text inline), `reading_order` (move the block one slot
 * earlier/later), and `block_structure` (suppress the block) — each of which
 * drafts a single generated `PatchOperation`. A per-correction reason is
 * required before it can be added to the drawer.
 */
export function CorrectionPanel({
  block,
  blockIndex,
  blockCount,
  rawBlocks,
  onAdd,
}: CorrectionPanelProps) {
  const editable = useMemo(() => firstEditableText(block), [block]);
  const canEditText = editable !== null;
  const canReorder = blockCount > 1;

  const availableScopes = useMemo<ReviewScope[]>(() => {
    const scopes: ReviewScope[] = [];
    if (canEditText) scopes.push('text');
    if (canReorder) scopes.push('reading_order');
    scopes.push('block_structure');
    return scopes;
  }, [canEditText, canReorder]);

  const [scope, setScope] = useState<ReviewScope>(availableScopes[0]);
  const activeScope = availableScopes.includes(scope) ? scope : availableScopes[0];

  const [textValue, setTextValue] = useState(editable?.text ?? '');
  const [direction, setDirection] = useState<ReorderDirection>(
    blockIndex === 0 ? 'later' : 'earlier',
  );
  const [reason, setReason] = useState('');

  // Reset editable defaults whenever the selected block changes.
  const blockKey = block.id;
  const [lastBlockKey, setLastBlockKey] = useState(blockKey);
  if (lastBlockKey !== blockKey) {
    setLastBlockKey(blockKey);
    setTextValue(editable?.text ?? '');
    setScope(availableScopes[0]);
    setDirection(blockIndex === 0 ? 'later' : 'earlier');
    setReason('');
  }

  const directionValid =
    activeScope !== 'reading_order' ||
    (direction === 'earlier' ? blockIndex > 0 : blockIndex < blockCount - 1);
  const textValid = activeScope !== 'text' || textValue.trim() !== '';
  const canAdd = reason.trim() !== '' && directionValid && textValid;

  function handleAdd() {
    if (!canAdd) return;
    let operation;
    let summary: string;
    if (activeScope === 'text' && editable) {
      operation = buildTextOp(blockIndex, editable.inlineIndex, textValue);
      summary = `Text: "${truncate(editable.text)}" → "${truncate(textValue)}"`;
    } else if (activeScope === 'reading_order') {
      operation = buildReorderOp(rawBlocks, blockIndex, direction);
      summary = `Reading order: move block ${blockIndex + 1} ${direction}`;
    } else {
      operation = buildSuppressOp(blockIndex);
      summary = `Suppress block ${blockIndex + 1} (${block.kind})`;
    }
    onAdd({
      id: nextEntryId(activeScope),
      scope: activeScope,
      blockRef: block.id,
      blockIndex,
      reason: reason.trim(),
      summary,
      operation,
    });
    setReason('');
  }

  return (
    <div className="review-correction-panel">
      <h3 className="review-panel-title">
        Correct block {blockIndex + 1} <span className="review-panel-kind">({block.kind})</span>
      </h3>

      <fieldset className="review-scope-fieldset">
        <legend>Correction type</legend>
        {availableScopes.map((s) => (
          <label key={s} className="review-scope-radio">
            <input
              type="radio"
              name="review-scope"
              value={s}
              checked={activeScope === s}
              onChange={() => setScope(s)}
            />
            {SCOPE_LABELS[s]}
          </label>
        ))}
      </fieldset>

      {activeScope === 'text' && (
        <label className="review-field">
          <span>Corrected text</span>
          <textarea
            className="review-text-input"
            value={textValue}
            onChange={(e) => setTextValue(e.target.value)}
            rows={3}
          />
        </label>
      )}

      {activeScope === 'reading_order' && (
        <fieldset className="review-scope-fieldset">
          <legend>Direction</legend>
          <label className="review-scope-radio">
            <input
              type="radio"
              name="review-direction"
              value="earlier"
              checked={direction === 'earlier'}
              disabled={blockIndex === 0}
              onChange={() => setDirection('earlier')}
            />
            Move earlier
          </label>
          <label className="review-scope-radio">
            <input
              type="radio"
              name="review-direction"
              value="later"
              checked={direction === 'later'}
              disabled={blockIndex >= blockCount - 1}
              onChange={() => setDirection('later')}
            />
            Move later
          </label>
        </fieldset>
      )}

      {activeScope === 'block_structure' && (
        <p className="review-suppress-note">
          Marks block {blockIndex + 1} for removal from the rendered page.
        </p>
      )}

      <label className="review-field">
        <span>Reason (required)</span>
        <input
          type="text"
          className="review-reason-input"
          value={reason}
          maxLength={280}
          placeholder="Why this correction is needed…"
          onChange={(e) => setReason(e.target.value)}
        />
      </label>

      <button
        type="button"
        className="review-add-button"
        disabled={!canAdd}
        onClick={handleAdd}
      >
        Add correction
      </button>
    </div>
  );
}

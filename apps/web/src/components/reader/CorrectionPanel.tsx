import type { RenderBlock } from '../../lib/render/types';
import type { PatchScope } from '../../lib/patch/schema';

interface Props {
  selectedIndex: number | null;
  selectedBlock: RenderBlock | null;
  correctionText: string;
  correctionScope: PatchScope;
  blockCount: number;
  onScopeChange: (s: PatchScope) => void;
  onTextChange: (t: string) => void;
  onAdd: () => void;
  onMove: (dir: -1 | 1) => void;
  onSuppress: () => void;
  pendingTextOpReady: boolean;
}

function getBlockLabel(block: RenderBlock, idx: number): string {
  const anyB = block as any;
  const kind = anyB.kind || 'block';
  const ch = Array.isArray(anyB.children) ? anyB.children : [];
  const t = ch.find((c: any) => c && c.kind === 'text');
  const preview = t ? (t.text || '').slice(0, 48) : '';
  return `${kind}#${idx}${preview ? ` — ${preview}` : ''}`;
}

export function CorrectionPanel({
  selectedIndex,
  selectedBlock,
  correctionText,
  correctionScope,
  blockCount,
  onScopeChange,
  onTextChange,
  onAdd,
  onMove,
  onSuppress,
  pendingTextOpReady,
}: Props) {
  if (!selectedBlock || selectedIndex == null) return null;

  return (
    <div className="review-correction-panel">
      <div>
        <strong>Selected:</strong> {getBlockLabel(selectedBlock, selectedIndex)}
      </div>

      <div style={{ margin: '8px 0' }}>
        <label>
          Scope
          <select
            value={correctionScope}
            onChange={(e) => onScopeChange(e.target.value as PatchScope)}
            style={{ marginLeft: 8 }}
          >
            <option value="text">text (correct inline text)</option>
            <option value="block_structure">block_structure (suppress block)</option>
            <option value="reading_order" disabled>
              reading_order (use Move up/down)
            </option>
          </select>
        </label>
      </div>

      {correctionScope === 'text' && (
        <div>
          <label>
            Corrected text
            <textarea
              value={correctionText}
              onChange={(e) => onTextChange(e.target.value)}
              rows={2}
              placeholder="Enter replacement text for the first text child…"
            />
          </label>
        </div>
      )}

      <div className="review-correction-actions">
        <button type="button" onClick={onAdd} disabled={!pendingTextOpReady && correctionScope !== 'block_structure'}>
          Add operation
        </button>
        <button type="button" onClick={() => onMove(-1)} disabled={selectedIndex === 0}>
          Move ↑ (order)
        </button>
        <button type="button" onClick={() => onMove(1)} disabled={selectedIndex === blockCount - 1}>
          Move ↓ (order)
        </button>
        <button type="button" onClick={onSuppress} disabled={selectedIndex == null}>
          Suppress block
        </button>
      </div>
      <div style={{ fontSize: '0.7rem', marginTop: 4, opacity: 0.7 }}>
        Operations target JSON Pointers inside the render_page payload (target_kind=render_page).
      </div>
    </div>
  );
}

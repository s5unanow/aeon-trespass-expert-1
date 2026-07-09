import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderBlock, RenderPageData } from '../lib/render/types';
import { ReviewFacsimileOverlay } from '../components/reader/ReviewFacsimileOverlay';
import { CorrectionPanel } from '../components/reader/CorrectionPanel';
import {
  createTextCorrectionOp,
  createBlockSuppressOp,
  createReadingOrderOps,
  opsAreInBounds,
  isExportablePatch,
} from '../lib/patch/pointer';
import {
  ensureDraftForPage,
  saveDraft,
  clearDraft,
} from '../lib/patch/draftStore';
import { downloadPatch } from '../lib/patch/download';
import type { PatchDraft, PatchOp, PatchScope } from '../lib/patch/schema';

/**
 * S5U-1538: Extraction review route.
 * Side-by-side facsimile (with per-block bbox overlays) + rendered blocks.
 * Drafts PatchSetV1 operations for text / reading_order / block_structure.
 * Persists to localStorage; exports typed JSON matching the pipeline contract.
 *
 * The route is lazy-loaded (see router.tsx) so the primary reader bundle size
 * is unaffected.
 */

function getFirstTextChildIndex(block: RenderBlock): number | null {
  const anyBlock = block as any;
  const children: any[] = Array.isArray(anyBlock.children) ? anyBlock.children : [];
  const idx = children.findIndex((c: any) => c && c.kind === 'text' && typeof c.text === 'string');
  return idx >= 0 ? idx : null;
}

function getBlockLabel(block: RenderBlock, idx: number): string {
  const anyB = block as any;
  const kind = anyB.kind || 'block';
  const ch = Array.isArray(anyB.children) ? anyB.children : [];
  const t = ch.find((c: any) => c && c.kind === 'text');
  const preview = t ? (t.text || '').slice(0, 48) : '';
  return `${kind}#${idx}${preview ? ` — ${preview}` : ''}`;
}

export function ReviewPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();

  const [page, setPage] = useState<RenderPageData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  // Draft state (restored from localStorage or fresh)
  const [draft, setDraft] = useState<PatchDraft | null>(null);

  // Transient UI state for the correction form
  const [correctionText, setCorrectionText] = useState('');
  const [correctionScope, setCorrectionScope] = useState<PatchScope>('text');
  const [authorInput, setAuthorInput] = useState('');
  const [reasonInput, setReasonInput] = useState('');

  // Load the render page (same loader as ReaderPage — committed fixture friendly)
  useEffect(() => {
    if (!documentId || !pageId || !edition) return;
    const controller = new AbortController();
    let stale = false;
    setPage(null);
    setError(null);
    loadRenderPage(documentId, pageId, edition, controller.signal)
      .then((data) => {
        if (!stale) {
          setPage(data);
          // Initialize (or restore) draft
          const initial = ensureDraftForPage({
            documentId,
            edition,
            pageId,
            initialAuthor: '',
            loadedPageMeta: { confidence: null }, // page meta may carry in future; optional today
          });
          setDraft(initial);
          // Seed form fields from restored draft if present
          if (initial.author) setAuthorInput(initial.author);
          if (initial.reason) setReasonInput(initial.reason);
        }
      })
      .catch((e) => {
        if (!stale && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  // Persist draft on change (keyed by doc/edition/page)
  useEffect(() => {
    if (!draft || !documentId || !edition || !pageId) return;
    // Keep form inputs reflected into the draft before save
    const next: PatchDraft = {
      ...draft,
      author: authorInput || draft.author || '',
      reason: reasonInput || draft.reason || '',
      operations: draft.operations ?? [],
    };
    setDraft(next); // local echo
    saveDraft(documentId, edition, pageId, next);
  }, [draft?.operations, authorInput, reasonInput, documentId, edition, pageId]); // eslint intentional — we trigger on meaningful fields

  const blocks: RenderBlock[] = page?.blocks ?? [];
  const blockCount = blocks.length;
  const selectedBlock: RenderBlock | null =
    selectedIndex != null ? blocks[selectedIndex] ?? null : null;

  const handleSelectBlock = useCallback((idx: number) => {
    setSelectedIndex(idx);
    setCorrectionText('');
    setCorrectionScope('text');
  }, []);

  const handleRegionClick = useCallback((idx: number) => {
    handleSelectBlock(idx);
  }, [handleSelectBlock]);

  // Hover sync: highlight matching region when hovering list item (and vice versa via class)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Build a pending op from the form (for the selected block)
  const pendingOp: PatchOp | null = useMemo(() => {
    if (selectedIndex == null || !selectedBlock) return null;
    if (correctionScope === 'text') {
      const childIdx = getFirstTextChildIndex(selectedBlock);
      if (childIdx == null || !correctionText.trim()) return null;
      try {
        return createTextCorrectionOp(selectedIndex, childIdx, correctionText.trim());
      } catch {
        return null;
      }
    }
    if (correctionScope === 'block_structure') {
      return createBlockSuppressOp(selectedIndex);
    }
    return null;
  }, [selectedIndex, selectedBlock, correctionScope, correctionText]);

  const addPendingOp = useCallback(() => {
    if (!pendingOp || !draft) return;
    // Guard: out of bounds vs current known count (original snapshot)
    if (!opsAreInBounds([pendingOp], blockCount)) return;

    const nextOps = [...(draft.operations ?? []), pendingOp];
    const nextDraft: PatchDraft = { ...draft, operations: nextOps };
    setDraft(nextDraft);
    // reset the text input for next correction
    setCorrectionText('');
  }, [pendingOp, draft, blockCount]);

  // Reading order helpers (move selected earlier/later)
  const moveSelected = useCallback(
    (direction: -1 | 1) => {
      if (selectedIndex == null || !draft || blockCount < 2) return;
      const from = selectedIndex;
      const to = Math.max(0, Math.min(blockCount - 1, from + direction));
      if (to === from) return;

      // Build reorder ops (delete+insert). Enrich the insert with the real block value
      // so that a consumer applying the patch has the moved object.
      const rawOps = createReadingOrderOps(from, to, blockCount);
      if (rawOps.length === 0) return;

      const blockValue = blocks[from];
      const enriched = rawOps.map((op) =>
        op.op === 'insert'
          ? { ...op, value: JSON.parse(JSON.stringify(blockValue)) } // deep copy for safety
          : op,
      );

      if (!opsAreInBounds(enriched, blockCount)) return;

      const nextOps = [...(draft.operations ?? []), ...enriched];
      const nextDraft: PatchDraft = { ...draft, operations: nextOps };
      setDraft(nextDraft);
      // After reorder the visual selection stays on logical original; the list still reflects original indices.
      // (MVP simplification — a fuller impl would re-index live preview.)
    },
    [selectedIndex, draft, blockCount, blocks],
  );

  const addStructureSuppress = useCallback(() => {
    if (selectedIndex == null || !draft) return;
    const op = createBlockSuppressOp(selectedIndex);
    if (!opsAreInBounds([op], blockCount)) return;
    const nextDraft: PatchDraft = { ...draft, operations: [...(draft.operations ?? []), op] };
    setDraft(nextDraft);
  }, [selectedIndex, draft, blockCount]);

  // Accumulate the pending text op
  const handleAddCorrection = useCallback(() => {
    if (pendingOp) addPendingOp();
    else if (correctionScope === 'block_structure') addStructureSuppress();
  }, [pendingOp, addPendingOp, correctionScope, addStructureSuppress]);

  // Remove last op (simple undo for MVP)
  const removeLastOp = useCallback(() => {
    if (!draft || (draft.operations ?? []).length === 0) return;
    const nextOps = (draft.operations ?? []).slice(0, -1);
    setDraft({ ...draft, operations: nextOps });
  }, [draft]);

  // Export
  const canExport = useMemo(() => {
    if (!draft) return false;
    const ops = draft.operations ?? [];
    const withForm = {
      operations: ops,
      reason: reasonInput || draft.reason,
      author: authorInput || draft.author,
    };
    return isExportablePatch(withForm) && opsAreInBounds(ops, blockCount);
  }, [draft, authorInput, reasonInput, blockCount]);

  const handleExport = useCallback(() => {
    if (!draft || !documentId || !edition || !pageId || !canExport) return;
    const ops = draft.operations ?? [];
    const finalDraft: PatchDraft = {
      ...draft,
      operations: ops,
      author: authorInput.trim() || draft.author || '',
      reason: reasonInput.trim() || draft.reason || '',
      // Ensure provenance is filled
      provenance: {
        author: authorInput.trim() || draft.author || '',
        created_at: (draft.provenance?.created_at || new Date().toISOString()) as any,
        source_confidence: draft.provenance?.source_confidence ?? null,
        expected_confidence_delta: null,
      },
    };
    downloadPatch(finalDraft);
    // Keep the draft after export (user may iterate); clear only on explicit reset if desired.
  }, [draft, authorInput, reasonInput, canExport, documentId, edition, pageId]);

  const handleClearDraft = useCallback(() => {
    if (!documentId || !edition || !pageId) return;
    clearDraft(documentId, edition, pageId);
    const fresh = ensureDraftForPage({ documentId, edition, pageId });
    setDraft(fresh);
    setAuthorInput('');
    setReasonInput('');
    setSelectedIndex(null);
    setCorrectionText('');
  }, [documentId, edition, pageId]);

  if (error) {
    return <div role="alert">Error loading page for review: {error}</div>;
  }
  if (!page || !draft) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading review page">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }

  const currentOps = draft.operations ?? [];

  return (
    <div className="review-page fade-in">
      <header>
        <h2 style={{ margin: 0 }}>
          Extraction Review — {documentId} / {edition} / {pageId}
        </h2>
        <p style={{ margin: '4px 0 0', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
          Draft a <code>patch_set.v1</code> targeting <code>render_page</code>. Changes are client-only until exported.
        </p>
      </header>

      <div className="review-split">
        {/* Facsimile side with per-block overlays (synthetic regions for fixtures without real bboxes) */}
        <div className="review-facsimile-panel">
          <h3>Facsimile (raster + block overlays)</h3>
          <ReviewFacsimileOverlay
            blocks={blocks}
            selectedIndex={selectedIndex}
            hoverIndex={hoverIndex}
            hasFacsimile={!!page.facsimile}
            onRegionClick={handleRegionClick}
            onHover={setHoverIndex}
          />
          {page.facsimile ? (
            <img
              src={page.facsimile.raster_src}
              alt={`Facsimile for ${pageId}`}
              style={{ width: '100%', height: 'auto', display: 'block', marginTop: 4 }}
            />
          ) : null}
          <div style={{ fontSize: '0.75rem', marginTop: 6, opacity: 0.7 }}>
            Click a numbered region or a block in the list. Hover syncs both sides.
          </div>
        </div>

        {/* Rendered blocks list + selection */}
        <div className="review-blocks-panel">
          <h3>Rendered blocks (click to select)</h3>
          <div className="review-blocks-list">
            {blocks.map((block, idx) => (
              <div
                key={block.id ?? idx}
                className={`review-block-item${selectedIndex === idx ? ' is-selected' : ''}`}
                onClick={() => handleSelectBlock(idx)}
                onMouseEnter={() => setHoverIndex(idx)}
                onMouseLeave={() => setHoverIndex(null)}
                id={`review-block-${idx}`}
              >
                <span className="block-kind">{(block as any).kind}</span>
                <span>{getBlockLabel(block, idx)}</span>
                <div style={{ fontSize: '0.65rem', opacity: 0.6, marginTop: 2 }}>{block.id}</div>
              </div>
            ))}
            {blocks.length === 0 && <div style={{ padding: 8 }}>No blocks on this page.</div>}
          </div>

          {/* Correction panel for the selected block */}
          <CorrectionPanel
            selectedIndex={selectedIndex}
            selectedBlock={selectedBlock}
            correctionText={correctionText}
            correctionScope={correctionScope}
            blockCount={blockCount}
            onScopeChange={setCorrectionScope}
            onTextChange={setCorrectionText}
            onAdd={handleAddCorrection}
            onMove={moveSelected}
            onSuppress={addStructureSuppress}
            pendingTextOpReady={!!pendingOp}
          />
        </div>
      </div>

      {/* Patch set drawer */}
      <div className="patch-drawer">
        <header>
          <strong>Patch set draft</strong>
          <span style={{ fontSize: '0.8rem' }}>
            {currentOps.length} op{currentOps.length === 1 ? '' : 's'} • {draft.patch_id}
          </span>
        </header>

        <div className="patch-op-list" aria-live="polite">
          {currentOps.length === 0 && <div style={{ opacity: 0.6 }}>(no operations yet — select a block and add corrections)</div>}
          {currentOps.map((op, i) => (
            <div key={i} className="op">
              {i + 1}. {op.op} {op.path} {op.scope ? `(scope: ${op.scope})` : ''}
              {op.value != null && typeof op.value !== 'object' ? ` → ${JSON.stringify(op.value).slice(0, 60)}` : ''}
            </div>
          ))}
        </div>

        <div className="patch-meta">
          <input
            type="text"
            placeholder="Author (required for export)"
            value={authorInput}
            onChange={(e) => setAuthorInput(e.target.value)}
          />
          <input
            type="text"
            placeholder="Reason (required for export)"
            value={reasonInput}
            onChange={(e) => setReasonInput(e.target.value)}
          />
        </div>

        <div className="patch-actions">
          <button type="button" onClick={handleExport} disabled={!canExport}>
            Export patch-{documentId}-{edition}-{pageId}-*.json
          </button>
          <button type="button" onClick={removeLastOp} disabled={currentOps.length === 0}>
            Undo last op
          </button>
          <button type="button" onClick={handleClearDraft}>
            Clear draft
          </button>
        </div>

        <p className="patch-hint">
          Draft survives reload (localStorage). Export produces a file the pipeline ingests via <code>PatchSetV1</code> + <code>apply_patches</code>.
          Client guards block export until reason, author, and ≥1 in-bounds op are present.
        </p>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import type { PatchSetV1 } from '@atr/schemas';
import '../styles/review.css';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { PageGlossaryProvider } from '../contexts/PageContext';
import { normalizeRenderPage } from '../lib/render/normalize';
import type { FacsimileAnnotation, RenderPageData } from '../lib/render/types';
import {
  buildPatchSet,
  buildReadingOrderOperations,
  buildSuppressBlockOperation,
  buildTextCorrectionOperation,
  downloadPatchSet,
  resolveJsonPointer,
  type ReviewPatchOperation,
} from '../lib/patch-review/export';

interface ReviewDraft {
  author: string;
  reason: string;
  operations: ReviewPatchOperation[];
}

interface ReviewPageState {
  normalized: RenderPageData;
  raw: unknown;
}

const EMPTY_DRAFT: ReviewDraft = { author: '', reason: '', operations: [] };

function draftKey(documentId: string, edition: string, pageId: string): string {
  return `atr:patch-review:${documentId}:${edition}:${pageId}`;
}

async function loadReviewPage(
  documentId: string,
  edition: string,
  pageId: string,
  signal: AbortSignal,
): Promise<ReviewPageState> {
  const editionUrl = `/documents/${documentId}/${edition}/data/render_page.${pageId}.json`;
  const rootUrl = `/documents/${documentId}/data/render_page.${pageId}.json`;
  let response = await fetch(editionUrl, { signal });
  if (!response.ok) {
    if (response.status !== 404) {
      throw new Error(`Edition fetch failed: ${response.status} ${editionUrl}`);
    }
    response = await fetch(rootUrl, { signal });
  }
  if (!response.ok) {
    throw new Error(`Failed to load render page: ${response.status} ${rootUrl}`);
  }
  const raw: unknown = await response.json();
  return { raw, normalized: normalizeRenderPage(raw) };
}

function sourceConfidence(raw: unknown): number | null {
  if (!raw || typeof raw !== 'object') return null;
  const record = raw as Record<string, unknown>;
  const direct = record.source_confidence;
  if (typeof direct === 'number') return direct;
  const page = record.page;
  if (page && typeof page === 'object') {
    const nested = (page as Record<string, unknown>).source_confidence;
    if (typeof nested === 'number') return nested;
  }
  return null;
}

function annotationArea(annotation: FacsimileAnnotation): number {
  const { bbox } = annotation;
  return Math.max(0, bbox.x1 - bbox.x0) * Math.max(0, bbox.y1 - bbox.y0);
}

function stackRanks(annotations: FacsimileAnnotation[]): number[] {
  const indexed = annotations.map((annotation, index) => ({ index, area: annotationArea(annotation) }));
  indexed.sort((a, b) => b.area - a.area);
  const ranks = Array.from({ length: annotations.length }, () => 0);
  indexed.forEach(({ index }, rank) => {
    ranks[index] = rank;
  });
  return ranks;
}

export function ExtractionReviewPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
  const [state, setState] = useState<ReviewPageState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null);
  const [correctedText, setCorrectedText] = useState('');
  const [draft, setDraft] = useState<ReviewDraft>(EMPTY_DRAFT);
  const [hydratedKey, setHydratedKey] = useState<string | null>(null);
  const storageKey = documentId && edition && pageId ? draftKey(documentId, edition, pageId) : null;

  useEffect(() => {
    if (!documentId || !edition || !pageId) return;
    const controller = new AbortController();
    let stale = false;
    setState(null);
    setError(null);
    loadReviewPage(documentId, edition, pageId, controller.signal)
      .then((loaded) => {
        if (!stale) setState(loaded);
      })
      .catch((e: Error) => {
        if (!stale && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  useEffect(() => {
    if (!storageKey) return;
    const saved = window.localStorage.getItem(storageKey);
    if (!saved) {
      setDraft(EMPTY_DRAFT);
    } else {
      try {
        setDraft(JSON.parse(saved) as ReviewDraft);
      } catch {
        setDraft(EMPTY_DRAFT);
      }
    }
    setHydratedKey(storageKey);
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey || hydratedKey !== storageKey) return;
    window.localStorage.setItem(storageKey, JSON.stringify(draft));
  }, [draft, hydratedKey, storageKey]);

  const page = state?.normalized;
  const selectedIndex = useMemo(() => {
    if (!page || !selectedBlockId) return -1;
    return page.blocks.findIndex((block) => block.id === selectedBlockId);
  }, [page, selectedBlockId]);
  const annotations = useMemo(
    () => [...((page?.facsimile?.annotations ?? []) as FacsimileAnnotation[])],
    [page?.facsimile?.annotations],
  );
  const ranks = useMemo(() => stackRanks(annotations), [annotations]);
  const canExport = draft.author.trim() && draft.reason.trim() && draft.operations.length > 0;

  const selectBlock = useCallback((blockId: string) => {
    setSelectedBlockId(blockId);
  }, []);

  const addOperations = useCallback(
    (operations: ReviewPatchOperation[]) => {
      if (!state) return;
      operations.forEach((op) => resolveJsonPointer(state.raw, op.path));
      setDraft((current) => ({
        ...current,
        operations: [...current.operations, ...operations],
      }));
    },
    [state],
  );

  const draftTextCorrection = useCallback(() => {
    if (!page || selectedIndex < 0 || !correctedText.trim()) return;
    addOperations([buildTextCorrectionOperation(page, selectedIndex, correctedText)]);
    setCorrectedText('');
  }, [addOperations, correctedText, page, selectedIndex]);

  const draftReadingOrder = useCallback(
    (direction: 'earlier' | 'later') => {
      if (!page || selectedIndex < 0) return;
      addOperations(buildReadingOrderOperations(page, selectedIndex, direction));
    },
    [addOperations, page, selectedIndex],
  );

  const draftSuppressBlock = useCallback(() => {
    if (!page || selectedIndex < 0) return;
    addOperations([buildSuppressBlockOperation(page, selectedIndex)]);
  }, [addOperations, page, selectedIndex]);

  const exportPatch = useCallback(() => {
    if (!documentId || !edition || !pageId || !state) return;
    const patchSet: PatchSetV1 = buildPatchSet({
      documentId,
      edition,
      pageId,
      page: state.normalized,
      operations: draft.operations,
      author: draft.author,
      reason: draft.reason,
      sourceConfidence: sourceConfidence(state.raw),
    });
    downloadPatchSet(patchSet, documentId, edition, pageId);
  }, [documentId, draft, edition, pageId, state]);

  if (error) return <div role="alert">Error: {error}</div>;
  if (!page) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading extraction review">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }

  return (
    <PageGlossaryProvider mentions={page.glossary_mentions}>
      <article className="review-page">
        <header className="review-header">
          <h1>Extraction review</h1>
          <p>{page.page.title}</p>
        </header>
        <div className="review-shell">
          <section className="review-facsimile" aria-label="Facsimile block overlays">
            {page.facsimile ? (
              <div className="review-facsimile-viewport">
                <img
                  src={page.facsimile.raster_src}
                  alt={`Page ${page.page.source_page_number}: ${page.page.title}`}
                  width={page.facsimile.width_px || undefined}
                  height={page.facsimile.height_px || undefined}
                />
                <div className="review-overlay">
                  {annotations.map((annotation, index) => {
                    const block = page.blocks[index];
                    if (!block) return null;
                    const { bbox } = annotation;
                    const active = selectedBlockId === block.id;
                    return (
                      <button
                        key={block.id}
                        type="button"
                        className={`review-bbox${active ? ' is-selected' : ''}`}
                        style={{
                          left: `${bbox.x0 * 100}%`,
                          top: `${bbox.y0 * 100}%`,
                          width: `${(bbox.x1 - bbox.x0) * 100}%`,
                          height: `${(bbox.y1 - bbox.y0) * 100}%`,
                          zIndex: active ? 1000 : 1 + (ranks[index] ?? 0),
                        }}
                        aria-label={`Select block ${block.id}`}
                        onMouseEnter={() => setHoveredBlockId(block.id)}
                        onMouseLeave={() => setHoveredBlockId(null)}
                        onClick={() => selectBlock(block.id)}
                      >
                        {index + 1}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <p>No facsimile raster is available for this page.</p>
            )}
          </section>

          <section className="review-rendered" aria-label="Rendered blocks">
            {page.blocks.map((block, index) => (
              <div
                key={block.id}
                className={[
                  'review-block',
                  selectedBlockId === block.id ? 'is-selected' : '',
                  hoveredBlockId === block.id ? 'is-hovered' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                data-review-block-id={block.id}
                onMouseEnter={() => setHoveredBlockId(block.id)}
                onMouseLeave={() => setHoveredBlockId(null)}
                onClick={() => selectBlock(block.id)}
              >
                <span className="review-block-index">{index + 1}</span>
                <BlockRenderer block={block} figures={page.figures} />
              </div>
            ))}
          </section>

          <aside className="review-panel" aria-label="Patch drawer">
            <label>
              <span>Author</span>
              <input
                value={draft.author}
                onChange={(e) => setDraft((current) => ({ ...current, author: e.target.value }))}
              />
            </label>
            <label>
              <span>Patch reason</span>
              <textarea
                value={draft.reason}
                onChange={(e) => setDraft((current) => ({ ...current, reason: e.target.value }))}
              />
            </label>
            {selectedIndex >= 0 ? (
              <section className="review-correction">
                <h2>Correct {page.blocks[selectedIndex].id}</h2>
                <label>
                  <span>Corrected text</span>
                  <textarea
                    value={correctedText}
                    onChange={(e) => setCorrectedText(e.target.value)}
                  />
                </label>
                <button type="button" onClick={draftTextCorrection}>
                  Draft text correction
                </button>
                <div className="review-button-row">
                  <button type="button" onClick={() => draftReadingOrder('earlier')}>
                    Move earlier
                  </button>
                  <button type="button" onClick={() => draftReadingOrder('later')}>
                    Move later
                  </button>
                </div>
                <button type="button" onClick={draftSuppressBlock}>
                  Suppress block
                </button>
              </section>
            ) : (
              <p>Select a block to draft a correction.</p>
            )}
            <section className="review-operations">
              <h2>Patch operations</h2>
              {draft.operations.length === 0 ? (
                <p>No operations drafted.</p>
              ) : (
                <ol>
                  {draft.operations.map((operation, index) => (
                    <li key={`${operation.path}-${index}`}>
                      <code>{operation.path}</code>
                      <span>{operation.scope}</span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <button type="button" disabled={!canExport} onClick={exportPatch}>
              Download patch JSON
            </button>
          </aside>
        </div>
      </article>
    </PageGlossaryProvider>
  );
}

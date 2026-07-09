import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import type { PatchSetV1 } from '@atr/schemas';
import { loadReviewPage } from '../lib/api/loadReviewPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockOverlay, type OverlayItem } from '../components/review/BlockOverlay';
import { ReviewBlockList } from '../components/review/ReviewBlockList';
import { CorrectionPanel } from '../components/review/CorrectionPanel';
import { PatchDrawer } from '../components/review/PatchDrawer';
import {
  clearDraft,
  draftStorageKey,
  loadDraft,
  saveDraft,
  type DraftEntry,
  type ReviewDraft,
} from '../lib/review/draft';
import {
  buildPatchFilename,
  buildPatchSet,
  collectExportErrors,
  type BuildPatchSetInput,
} from '../lib/review/patchSet';
import { downloadPatchSet } from '../lib/review/download';
// Imported here (not main.tsx) so the review styles ship in the lazy chunk and
// never grow the reader's initial CSS bundle (S5U-1539 acceptance #6).
import '../styles/review.css';

/**
 * render_page.v1 carries no page-confidence field, so `provenance.source_confidence`
 * stays null unless the schema later adds one — "source_confidence from page meta
 * when present" (S5U-1539). Kept as a seam for a future confidence field.
 */
function readSourceConfidence(_page: RenderPageData): number | null {
  return null;
}

export interface ReviewWorkspaceProps {
  documentId: string;
  edition: string;
  pageId: string;
  page: RenderPageData;
  rawBlocks: unknown[];
  /** Injected in tests to observe the export without touching the DOM. */
  download?: (patchSet: PatchSetV1, filename: string) => void;
  /** Injected in tests for a deterministic timestamp. */
  now?: () => Date;
}

/**
 * The interactive review surface. Mounted with a `key` of the storage key, so a
 * page change remounts it and its draft state is re-hydrated for the new page.
 */
export function ReviewWorkspace({
  documentId,
  edition,
  pageId,
  page,
  rawBlocks,
  download = downloadPatchSet,
  now = () => new Date(),
}: ReviewWorkspaceProps) {
  const storageKey = draftStorageKey(documentId, edition, pageId);
  const [draft, setDraft] = useState<ReviewDraft>(() => loadDraft(storageKey));
  const [hoveredRef, setHoveredRef] = useState<string | null>(null);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);

  // Persist on every draft change. `storageKey` is constant for this instance
  // (the parent remounts via `key` on page change), so this never crosses pages.
  useEffect(() => {
    saveDraft(storageKey, draft);
  }, [storageKey, draft]);

  const highlightRef = hoveredRef ?? selectedRef;

  const overlayItems = useMemo<OverlayItem[]>(() => {
    const annotations = page.facsimile?.annotations ?? [];
    const items: OverlayItem[] = [];
    annotations.forEach((ann, i) => {
      const block = page.blocks[i];
      if (!block) return; // more annotations than blocks — skip the extras
      items.push({ ref: block.id, bbox: ann.bbox, label: ann.translated_text || ann.text });
    });
    return items;
  }, [page.facsimile, page.blocks]);

  const selectedIndex = selectedRef ? page.blocks.findIndex((b) => b.id === selectedRef) : -1;
  const selectedBlock = selectedIndex >= 0 ? page.blocks[selectedIndex] : null;

  const errors = useMemo(() => collectExportErrors(draft, page), [draft, page]);

  const handleAdd = useCallback((entry: DraftEntry) => {
    setDraft((prev) => ({ ...prev, entries: [...prev.entries, entry] }));
  }, []);

  const handleRemove = useCallback((id: string) => {
    setDraft((prev) => ({ ...prev, entries: prev.entries.filter((e) => e.id !== id) }));
  }, []);

  const handleAuthor = useCallback((author: string) => {
    setDraft((prev) => ({ ...prev, author }));
  }, []);

  const handleExport = useCallback(() => {
    if (collectExportErrors(draft, page).length > 0) return;
    const input: BuildPatchSetInput = {
      documentId,
      edition,
      pageId,
      draft,
      sourceConfidence: readSourceConfidence(page),
      now: now(),
    };
    download(buildPatchSet(input), buildPatchFilename(input));
    clearDraft(storageKey);
    setDraft({ author: draft.author, entries: [] });
  }, [draft, page, documentId, edition, pageId, now, download, storageKey]);

  return (
    <div className="review-page">
      <header className="review-header">
        <h1 className="review-heading">
          Extraction review — {documentId} / {edition} / {pageId}
        </h1>
        <p className="review-subhead">
          Draft typed corrections as a downloadable <code>patch_set.v1</code>. Select a block on
          either side to correct it.
        </p>
      </header>

      <div className="review-body">
        <div className="review-split">
          <div className="review-pane review-facsimile-pane">
            {page.facsimile && overlayItems.length > 0 ? (
              <BlockOverlay
                raster={{
                  src: page.facsimile.raster_src,
                  srcHires: page.facsimile.raster_src_hires || undefined,
                  width: page.facsimile.width_px || undefined,
                  height: page.facsimile.height_px || undefined,
                  alt: `Facsimile of ${pageId}`,
                }}
                items={overlayItems}
                activeRef={highlightRef}
                onActivate={setSelectedRef}
                onHover={setHoveredRef}
              />
            ) : (
              <p className="review-no-facsimile">
                No facsimile raster for this page — correct blocks from the list.
              </p>
            )}
          </div>
          <div className="review-pane review-blocks-pane">
            <ReviewBlockList
              blocks={page.blocks}
              figures={page.figures}
              activeRef={highlightRef}
              onActivate={setSelectedRef}
              onHover={setHoveredRef}
            />
          </div>
        </div>

        <aside className="review-rail">
          {selectedBlock ? (
            <CorrectionPanel
              block={selectedBlock}
              blockIndex={selectedIndex}
              blockCount={page.blocks.length}
              rawBlocks={rawBlocks}
              onAdd={handleAdd}
            />
          ) : (
            <p className="review-no-selection">Select a block to draft a correction.</p>
          )}
          <PatchDrawer
            draft={draft}
            errors={errors}
            onAuthorChange={handleAuthor}
            onRemove={handleRemove}
            onActivate={setSelectedRef}
            onExport={handleExport}
          />
        </aside>
      </div>
    </div>
  );
}

/** Lazy route: `/documents/:documentId/:edition/review/:pageId`. */
export function ReviewPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
  const [load, setLoad] = useState<{ page: RenderPageData; rawBlocks: unknown[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId || !edition || !pageId) return;
    const controller = new AbortController();
    let stale = false;
    setLoad(null);
    setError(null);
    loadReviewPage(documentId, pageId, edition, controller.signal)
      .then((data) => {
        if (!stale) setLoad(data);
      })
      .catch((e: Error) => {
        if (!stale && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  if (!documentId || !edition || !pageId) {
    return <div role="alert">Missing route parameters.</div>;
  }
  if (error) {
    return <div role="alert">Error: {error}</div>;
  }
  if (!load) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading review page">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }

  return (
    <ReviewWorkspace
      key={`${documentId}:${edition}:${pageId}`}
      documentId={documentId}
      edition={edition}
      pageId={pageId}
      page={load.page}
      rawBlocks={load.rawBlocks}
    />
  );
}

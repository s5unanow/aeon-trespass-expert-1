import { useEffect, useMemo, useState } from 'react';
import type { patchSetV1 } from '@atr/schemas';
import type { RenderPageData } from '../../lib/render/types';
import { applyPatchOperations, buildPatchSet } from '../../lib/review/patches';
import { downloadPatchSet } from '../../lib/review/download';
import { loadReviewDraft, saveReviewDraft, type ReviewDraft } from '../../lib/review/persistence';
import { PageGlossaryProvider } from '../../contexts/PageContext';
import { CorrectionPanel } from './CorrectionPanel';
import { PatchDrawer } from './PatchDrawer';
import { ReviewBlocks } from './ReviewBlocks';
import { ReviewFacsimile } from './ReviewFacsimile';

interface ReviewWorkspaceProps {
  page: RenderPageData;
  documentId: string;
  edition: string;
  pageId: string;
  storageKey: string;
}

export function ReviewWorkspace({
  page,
  documentId,
  edition,
  pageId,
  storageKey,
}: ReviewWorkspaceProps) {
  const [initialDraft] = useState(() => loadReviewDraft(storageKey, page));
  const [operations, setOperations] = useState(initialDraft.operations);
  const [reason, setReason] = useState(initialDraft.reason);
  const [author, setAuthor] = useState(initialDraft.author);
  const [hoveredBlockRef, setHoveredBlockRef] = useState<string | null>(null);
  const [selectedBlockRef, setSelectedBlockRef] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const projectedPage = useMemo(
    () => applyPatchOperations(page, operations),
    [page, operations],
  );
  const selectedIndex = selectedBlockRef
    ? projectedPage.blocks.findIndex((block) => block.id === selectedBlockRef)
    : -1;
  const targetArtifactRef = page.build_meta?.artifact_ref ?? '';

  useEffect(() => {
    const draft: ReviewDraft = { operations, reason, author };
    saveReviewDraft(storageKey, draft);
  }, [storageKey, operations, reason, author]);

  function addOperation(operation: patchSetV1.PatchOperation) {
    setOperations((current) => {
      const next = [...current, operation];
      applyPatchOperations(page, next);
      return next;
    });
  }

  function exportPatch() {
    try {
      const patchSet = buildPatchSet(
        documentId,
        edition,
        pageId,
        targetArtifactRef,
        page,
        operations,
        reason,
        author,
        page.page.source_confidence,
        new Date(),
      );
      downloadPatchSet(patchSet);
      setExportError(null);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : 'Unable to export patch set');
    }
  }

  return (
    <PageGlossaryProvider mentions={page.glossary_mentions}>
      <article className="review-page">
        <header className="review-header">
          <div>
            <p className="review-eyebrow">
              {documentId} · {edition} · {pageId}
            </p>
            <h1>Extraction review</h1>
            <p>Compare the facsimile with rendered blocks, then draft typed corrections.</p>
          </div>
          {page.page.source_confidence !== null && (
            <span className="review-confidence">
              Source confidence {Math.round(page.page.source_confidence * 100)}%
            </span>
          )}
        </header>

        <div className="review-split">
          <section aria-labelledby="review-facsimile-title">
            <h2 id="review-facsimile-title">Facsimile</h2>
            {page.facsimile ? (
              <ReviewFacsimile
                facsimile={page.facsimile}
                pageTitle={page.page.title}
                pageNumber={page.page.source_page_number}
                activeBlockRef={hoveredBlockRef}
                selectedBlockRef={selectedBlockRef}
                onHover={setHoveredBlockRef}
                onSelect={setSelectedBlockRef}
              />
            ) : (
              <p role="alert">This page has no facsimile raster to review.</p>
            )}
          </section>
          <section aria-labelledby="review-rendered-title">
            <h2 id="review-rendered-title">Rendered blocks</h2>
            <ReviewBlocks
              blocks={page.blocks}
              figures={page.figures}
              activeBlockRef={hoveredBlockRef}
              selectedBlockRef={selectedBlockRef}
              onHover={setHoveredBlockRef}
              onSelect={setSelectedBlockRef}
            />
          </section>
        </div>

        {selectedIndex >= 0 && (
          <CorrectionPanel
            blocks={projectedPage.blocks}
            selectedIndex={selectedIndex}
            onAdd={addOperation}
          />
        )}
        <PatchDrawer
          operations={operations}
          reason={reason}
          author={author}
          targetReady={targetArtifactRef !== ''}
          exportError={exportError}
          onReasonChange={setReason}
          onAuthorChange={setAuthor}
          onRemove={(index) => setOperations((current) => current.filter((_, i) => i !== index))}
          onClear={() => setOperations([])}
          onExport={exportPatch}
        />
      </article>
    </PageGlossaryProvider>
  );
}

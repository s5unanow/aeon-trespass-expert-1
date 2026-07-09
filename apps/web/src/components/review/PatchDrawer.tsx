import type { patchSetV1 } from '@atr/schemas';

interface PatchDrawerProps {
  operations: patchSetV1.PatchOperation[];
  reason: string;
  author: string;
  targetReady: boolean;
  exportError: string | null;
  onReasonChange: (reason: string) => void;
  onAuthorChange: (author: string) => void;
  onRemove: (index: number) => void;
  onClear: () => void;
  onExport: () => void;
}

export function PatchDrawer({
  operations,
  reason,
  author,
  targetReady,
  exportError,
  onReasonChange,
  onAuthorChange,
  onRemove,
  onClear,
  onExport,
}: PatchDrawerProps) {
  const canExport =
    targetReady && operations.length > 0 && reason.trim() !== '' && author.trim() !== '';
  return (
    <aside className="review-patch-drawer" aria-labelledby="review-patch-title">
      <div className="review-patch-heading">
        <div>
          <h2 id="review-patch-title">Patch operations</h2>
          <p>
            {operations.length} {operations.length === 1 ? 'operation' : 'operations'}
          </p>
        </div>
        {operations.length > 0 && (
          <button type="button" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <ol className="review-operation-list">
        {operations.map((operation, index) => (
          <li key={`${operation.scope}-${operation.path}-${index}`}>
            <span>{operation.scope}</span>
            <code>{operation.path}</code>
            <button
              type="button"
              aria-label={`Remove operation ${index + 1}`}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </li>
        ))}
      </ol>
      <label>
        <span>Author</span>
        <input value={author} onChange={(event) => onAuthorChange(event.target.value)} />
      </label>
      <label>
        <span>Reason</span>
        <textarea
          rows={3}
          value={reason}
          onChange={(event) => onReasonChange(event.target.value)}
        />
      </label>
      <button type="button" disabled={!canExport} onClick={onExport}>
        Export patch JSON
      </button>
      <p className="review-export-hint">
        {targetReady
          ? 'Author, reason, and at least one operation are required.'
          : 'This exported page has no ingestible patch target. Re-export it from the pipeline.'}
      </p>
      {exportError && <p role="alert">{exportError}</p>}
    </aside>
  );
}

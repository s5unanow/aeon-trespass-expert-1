import type { ReviewDraft } from '../../lib/review/draft';

interface PatchDrawerProps {
  draft: ReviewDraft;
  /** Export blockers from `collectExportErrors` — empty means ready. */
  errors: string[];
  onAuthorChange: (author: string) => void;
  onRemove: (id: string) => void;
  onActivate: (ref: string) => void;
  onExport: () => void;
}

/**
 * Accumulates drafted corrections into a patch set. Requires an author and at
 * least one correction (each with a reason) before the download is enabled —
 * export blockers are surfaced inline.
 */
export function PatchDrawer({
  draft,
  errors,
  onAuthorChange,
  onRemove,
  onActivate,
  onExport,
}: PatchDrawerProps) {
  const canExport = errors.length === 0;

  return (
    <section className="review-drawer" aria-label="Patch set">
      <h2 className="review-drawer-title">
        Patch set <span className="review-drawer-count">({draft.entries.length})</span>
      </h2>

      <label className="review-field">
        <span>Author (required)</span>
        <input
          type="text"
          className="review-author-input"
          value={draft.author}
          maxLength={120}
          placeholder="Your name or handle"
          onChange={(e) => onAuthorChange(e.target.value)}
        />
      </label>

      {draft.entries.length === 0 ? (
        <p className="review-drawer-empty">No corrections yet. Select a block to start.</p>
      ) : (
        <ul className="review-entry-list">
          {draft.entries.map((entry) => (
            <li key={entry.id} className="review-entry" data-scope={entry.scope}>
              <button
                type="button"
                className="review-entry-summary"
                onClick={() => onActivate(entry.blockRef)}
                title={`Focus ${entry.blockRef}`}
              >
                <span className="review-entry-scope">{entry.scope}</span>
                <span className="review-entry-text">{entry.summary}</span>
                <span className="review-entry-reason">{entry.reason}</span>
              </button>
              <button
                type="button"
                className="review-entry-remove"
                aria-label={`Remove correction: ${entry.summary}`}
                onClick={() => onRemove(entry.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {errors.length > 0 && (
        <ul className="review-errors" role="alert">
          {errors.map((err) => (
            <li key={err}>{err}</li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="review-export-button"
        disabled={!canExport}
        onClick={onExport}
      >
        Download patch set
      </button>
      <p className="review-drawer-hint">
        Downloads a <code>patch_set.v1</code> JSON. Commit it under{' '}
        <code>artifacts/patches/</code> or attach it to the Linear issue — never edit the generated
        render output directly (ADR-003).
      </p>
    </section>
  );
}

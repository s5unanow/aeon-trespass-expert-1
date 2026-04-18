import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { FeedbackIssueType, FeedbackSubmission } from '../../lib/feedback/schema';
import { FEEDBACK_SCHEMA_VERSION } from '../../lib/feedback/schema';
import { downloadFeedback as defaultDownloadFeedback } from '../../lib/feedback/download';

interface FeedbackButtonProps {
  documentId: string;
  edition: string;
  pageId: string;
  /** Injected in tests so we can observe the submission without touching the DOM. */
  onDownload?: (submission: FeedbackSubmission) => void;
  /** Injected in tests to produce a deterministic timestamp. */
  now?: () => Date;
}

const ISSUE_TYPES: readonly FeedbackIssueType[] = [
  'translation',
  'extraction',
  'rendering',
  'other',
];

export function FeedbackButton({
  documentId,
  edition,
  pageId,
  onDownload,
  now,
}: FeedbackButtonProps) {
  const [open, setOpen] = useState(false);
  const [issueType, setIssueType] = useState<FeedbackIssueType>('translation');
  const [note, setNote] = useState('');
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const download = onDownload ?? defaultDownloadFeedback;
  const clock = now ?? (() => new Date());

  const closeDialog = useCallback(() => {
    setOpen(false);
    setNote('');
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDialog();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, closeDialog]);

  const handleOpen = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    // Prevent the click from propagating to underlying reader content (links, blocks).
    e.stopPropagation();
    setOpen(true);
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const submission: FeedbackSubmission = {
        schema_version: FEEDBACK_SCHEMA_VERSION,
        document_id: documentId,
        edition,
        page_id: pageId,
        issue_type: issueType,
        note: note.trim(),
        url: typeof window !== 'undefined' ? window.location.href : '',
        user_agent:
          typeof navigator !== 'undefined' && typeof navigator.userAgent === 'string'
            ? navigator.userAgent
            : '',
        timestamp: clock().toISOString(),
      };
      download(submission);
      closeDialog();
    },
    [documentId, edition, pageId, issueType, note, clock, download, closeDialog],
  );

  return (
    <>
      <button
        type="button"
        className="feedback-button"
        aria-label="Report issue"
        onClick={handleOpen}
      >
        Report issue
      </button>
      {open && (
        <div
          className="feedback-modal-backdrop"
          role="presentation"
          onClick={closeDialog}
          onKeyDown={() => {
            /* keyboard close is handled at window level via Escape */
          }}
        >
          <div
            ref={dialogRef}
            className="feedback-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id={titleId} className="feedback-modal-title">
              Report issue on this page
            </h2>
            <form onSubmit={handleSubmit}>
              <fieldset className="feedback-fieldset">
                <legend>Issue type</legend>
                {ISSUE_TYPES.map((t) => (
                  <label key={t} className="feedback-radio">
                    <input
                      type="radio"
                      name="feedback-issue-type"
                      value={t}
                      checked={issueType === t}
                      onChange={() => setIssueType(t)}
                    />
                    {t}
                  </label>
                ))}
              </fieldset>
              <label className="feedback-note">
                <span>Note (optional)</span>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={4}
                  maxLength={2000}
                  placeholder="Describe the issue…"
                />
              </label>
              <div className="feedback-actions">
                <button type="button" onClick={closeDialog}>
                  Cancel
                </button>
                <button type="submit">Download JSON</button>
              </div>
              <p className="feedback-hint">
                Downloads a JSON file. Commit it to <code>artifacts/feedback/</code> or attach to
                the Linear issue.
              </p>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

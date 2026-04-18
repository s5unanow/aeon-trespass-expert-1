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

/**
 * Selector for focusable elements within the dialog. Excludes elements that
 * are explicitly taken out of the tab order via `tabindex="-1"` or `disabled`.
 */
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function getFocusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute('disabled') && el.tabIndex !== -1,
  );
}

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
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();
  const download = onDownload ?? defaultDownloadFeedback;
  const clock = now ?? (() => new Date());

  const closeDialog = useCallback(() => {
    setOpen(false);
    setNote('');
  }, []);

  // On open: move focus into the dialog. On close: restore focus to the trigger.
  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusables = getFocusableElements(dialog);
    const target = focusables[0] ?? dialog;
    target.focus();
    return () => {
      // When the dialog closes, return focus to the element that opened it.
      triggerRef.current?.focus();
    };
  }, [open]);

  const handleDialogKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeDialog();
        return;
      }
      if (e.key !== 'Tab') return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusables = getFocusableElements(dialog);
      if (focusables.length === 0) {
        // No focusable children — keep focus inside the dialog itself.
        e.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last || !dialog.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [closeDialog],
  );

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
        ref={triggerRef}
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
        >
          <div
            ref={dialogRef}
            className="feedback-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={handleDialogKeyDown}
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

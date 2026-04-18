// Trigger a browser download of a JSON blob. Factored out of the component
// so tests can mock it without touching DOM internals.
import type { FeedbackSubmission } from './schema';
import { buildFeedbackFilename } from './schema';

export function downloadFeedback(submission: FeedbackSubmission): void {
  const json = JSON.stringify(submission, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildFeedbackFilename(submission);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

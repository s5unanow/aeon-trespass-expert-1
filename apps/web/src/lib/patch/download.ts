// Trigger a browser download of a PatchSetV1 JSON blob.
// Factored out of the component (mirrors lib/feedback/download.ts) so tests
// can mock it without touching DOM.

import type { PatchDraft } from './schema';
import { buildPatchFilename } from './schema';

export function downloadPatch(patch: PatchDraft): void {
  const json = JSON.stringify(patch, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildPatchFilename(patch);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

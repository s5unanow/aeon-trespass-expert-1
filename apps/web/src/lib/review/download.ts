// Trigger a browser download of a patch-set JSON blob. Factored out of the
// component so tests can inject a spy without touching DOM internals — mirrors
// `lib/feedback/download.ts`.
import type { PatchSetV1 } from '@atr/schemas';

export function downloadPatchSet(patchSet: PatchSetV1, filename: string): void {
  const json = JSON.stringify(patchSet, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

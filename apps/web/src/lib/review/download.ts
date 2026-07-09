import type { PatchSetV1 } from '@atr/schemas';
import { buildPatchFilename } from './patches';

export function downloadPatchSet(patchSet: PatchSetV1): void {
  const json = JSON.stringify(patchSet, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildPatchFilename(patchSet);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

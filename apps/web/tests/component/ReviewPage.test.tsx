import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import type { PatchSetV1 } from '@atr/schemas';
import { ReviewWorkspace } from '../../src/routes/ReviewPage';
import { normalizeRenderPage } from '../../src/lib/render/normalize';
import fixture from '../../public/documents/review_sample/en/data/render_page.p0001.json';

const page = normalizeRenderPage(fixture);
const rawBlocks = fixture.blocks as unknown[];
const NOW = new Date('2026-07-09T12:00:00.000Z');

// GlossaryText (via BlockRenderer) calls useNavigate/useParams, so a Router
// context is required. Production supplies it through ReaderLayout's route.
function renderWorkspace(download: (p: PatchSetV1, filename: string) => void) {
  return render(
    <MemoryRouter>
      <ReviewWorkspace
        documentId="review_sample"
        edition="en"
        pageId="p0001"
        page={page}
        rawBlocks={rawBlocks}
        download={download}
        now={() => NOW}
      />
    </MemoryRouter>,
  );
}

/** Draft a text correction on block 2 (paragraph b002). */
function draftTextCorrectionOnBlock2(newText: string, reason: string) {
  fireEvent.click(screen.getByRole('button', { name: /Select block 2/ }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Corrected text' }), {
    target: { value: newText },
  });
  fireEvent.change(screen.getByRole('textbox', { name: 'Reason (required)' }), {
    target: { value: reason },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add correction' }));
}

afterEach(cleanup);
beforeEach(() => localStorage.clear());

describe('ReviewWorkspace', () => {
  it('syncs selection between the facsimile overlay and the block list', () => {
    renderWorkspace(vi.fn());
    // Selecting a block from the list marks the matching overlay marker active.
    fireEvent.click(screen.getByRole('button', { name: /Select block 2/ }));
    const marker = screen.getByRole('button', { name: /^Block 2:/ });
    expect(marker.getAttribute('aria-pressed')).toBe('true');

    // Clicking a different overlay marker moves the highlight (same block ref).
    const marker1 = screen.getByRole('button', { name: /^Block 1:/ });
    fireEvent.click(marker1);
    expect(marker1.getAttribute('aria-pressed')).toBe('true');
    expect(marker.getAttribute('aria-pressed')).toBe('false');
  });

  it('drafts a text correction and blocks export until author is set', () => {
    const download = vi.fn();
    renderWorkspace(download);

    draftTextCorrectionOnBlock2("Roll dice equal to the titan's ATTACK value.", 'fix casing');

    // The drawer now lists one correction.
    const drawer = screen.getByRole('region', { name: 'Patch set' });
    expect(within(drawer).getByText(/Patch set/)).toBeDefined();
    expect(within(drawer).getByText(/fix casing/)).toBeDefined();

    // Export is blocked with no author.
    const exportBtn = screen.getByRole('button', {
      name: 'Download patch set',
    }) as HTMLButtonElement;
    expect(exportBtn.disabled).toBe(true);
    expect(within(drawer).getByRole('alert').textContent).toContain('Author is required');

    // Setting an author unblocks export.
    fireEvent.change(screen.getByRole('textbox', { name: 'Author (required)' }), {
      target: { value: 'reviewer' },
    });
    expect(exportBtn.disabled).toBe(false);
  });

  it('exports a schema-shaped patch set with the text operation', () => {
    const download = vi.fn<(p: PatchSetV1, filename: string) => void>();
    renderWorkspace(download);

    draftTextCorrectionOnBlock2("Roll dice equal to the titan's ATTACK value.", 'fix casing');
    fireEvent.change(screen.getByRole('textbox', { name: 'Author (required)' }), {
      target: { value: 'reviewer' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download patch set' }));

    expect(download).toHaveBeenCalledTimes(1);
    const [patchSet, filename] = download.mock.calls[0];
    expect(patchSet.schema_version).toBe('patch_set.v1');
    expect(patchSet.target_kind).toBe('render_page');
    expect(patchSet.author).toBe('reviewer');
    expect(patchSet.provenance?.author).toBe('reviewer');
    expect(patchSet.operations).toHaveLength(1);
    const op = patchSet.operations![0];
    expect(op.op).toBe('replace');
    expect(op.path).toBe('/blocks/1/children/0/text');
    expect(op.scope).toBe('text');
    expect(op.value).toBe("Roll dice equal to the titan's ATTACK value.");
    expect(filename).toBe('patch-review_sample-en-p0001-2026-07-09T12-00-00-000Z.json');
  });

  it('persists a drafted correction across a remount (reload)', () => {
    const { unmount } = renderWorkspace(vi.fn());
    draftTextCorrectionOnBlock2('corrected text here', 'fix casing');
    unmount();

    // A fresh instance hydrates the draft from localStorage.
    renderWorkspace(vi.fn());
    const drawer = screen.getByRole('region', { name: 'Patch set' });
    expect(within(drawer).getByText(/fix casing/)).toBeDefined();
    // Count is rendered in its own span next to the "Patch set" title.
    expect(within(drawer).getByText('(1)')).toBeDefined();
  });

  it('can suppress a block via the block_structure scope', () => {
    const download = vi.fn<(p: PatchSetV1, filename: string) => void>();
    renderWorkspace(download);

    fireEvent.click(screen.getByRole('button', { name: /Select block 4/ }));
    fireEvent.click(screen.getByRole('radio', { name: 'Suppress block' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason (required)' }), {
      target: { value: 'duplicated callout' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add correction' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Author (required)' }), {
      target: { value: 'reviewer' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download patch set' }));

    const [patchSet] = download.mock.calls[0];
    const op = patchSet.operations![0];
    expect(op.op).toBe('delete');
    expect(op.path).toBe('/blocks/3');
    expect(op.scope).toBe('block_structure');
  });
});

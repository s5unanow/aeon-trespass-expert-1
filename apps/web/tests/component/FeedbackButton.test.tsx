import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FeedbackButton } from '../../src/components/reader/FeedbackButton';
import type { FeedbackSubmission } from '../../src/lib/feedback/schema';

const baseProps = {
  documentId: 'ato_core_v1_1',
  edition: 'ru',
  pageId: 'p0042',
};

afterEach(() => {
  cleanup();
});

describe('FeedbackButton', () => {
  it('renders a labelled "Report issue" button', () => {
    const onDownload = vi.fn();
    render(<FeedbackButton {...baseProps} onDownload={onDownload} />);
    expect(screen.getByRole('button', { name: 'Report issue' })).toBeDefined();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens modal on click and closes via Cancel', () => {
    const onDownload = vi.fn();
    render(<FeedbackButton {...baseProps} onDownload={onDownload} />);
    fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
    expect(screen.getByRole('dialog')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('stops click propagation so underlying reader content is not activated', () => {
    const onDownload = vi.fn();
    const outerClick = vi.fn();
    const { container } = render(
      <div onClick={outerClick}>
        <FeedbackButton {...baseProps} onDownload={onDownload} />
      </div>,
    );
    const trigger = container.querySelector('button.feedback-button') as HTMLButtonElement;
    fireEvent.click(trigger);
    expect(outerClick).not.toHaveBeenCalled();
  });

  it('submits a structured payload including page_id, issue type, note and timestamp', () => {
    const onDownload = vi.fn<(s: FeedbackSubmission) => void>();
    const fixedNow = new Date('2026-04-18T12:34:56.000Z');
    render(<FeedbackButton {...baseProps} onDownload={onDownload} now={() => fixedNow} />);
    fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
    fireEvent.click(screen.getByLabelText('rendering'));
    fireEvent.change(screen.getByPlaceholderText(/Describe the issue/), {
      target: { value: '  Figure 3 overlaps caption  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }));

    expect(onDownload).toHaveBeenCalledTimes(1);
    const payload = onDownload.mock.calls[0][0];
    expect(payload.schema_version).toBe('user_feedback.v1');
    expect(payload.document_id).toBe('ato_core_v1_1');
    expect(payload.edition).toBe('ru');
    expect(payload.page_id).toBe('p0042');
    expect(payload.issue_type).toBe('rendering');
    expect(payload.note).toBe('Figure 3 overlaps caption');
    expect(payload.timestamp).toBe('2026-04-18T12:34:56.000Z');
    // Modal closes after submit.
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('allows submission with empty note', () => {
    const onDownload = vi.fn<(s: FeedbackSubmission) => void>();
    render(<FeedbackButton {...baseProps} onDownload={onDownload} />);
    fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
    fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }));
    expect(onDownload).toHaveBeenCalledTimes(1);
    expect(onDownload.mock.calls[0][0].note).toBe('');
  });

  describe('accessibility / focus management', () => {
    it('moves focus into the dialog on open (first focusable element)', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
      // First focusable element is the first radio input ("translation").
      const firstRadio = screen.getByLabelText('translation') as HTMLInputElement;
      expect(document.activeElement).toBe(firstRadio);
    });

    it('restores focus to the trigger when closing via Cancel', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      const trigger = screen.getByRole('button', { name: 'Report issue' });
      fireEvent.click(trigger);
      expect(screen.getByRole('dialog')).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(document.activeElement).toBe(trigger);
    });

    it('restores focus to the trigger when closing via Escape', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      const trigger = screen.getByRole('button', { name: 'Report issue' });
      fireEvent.click(trigger);
      const dialog = screen.getByRole('dialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(document.activeElement).toBe(trigger);
    });

    it('restores focus to the trigger when closing via submit', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      const trigger = screen.getByRole('button', { name: 'Report issue' });
      fireEvent.click(trigger);
      fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }));
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(document.activeElement).toBe(trigger);
    });

    it('traps Tab from the last focusable element back to the first', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
      const dialog = screen.getByRole('dialog');
      // The "Download JSON" submit button is the last focusable element.
      const lastFocusable = screen.getByRole('button', { name: 'Download JSON' });
      lastFocusable.focus();
      expect(document.activeElement).toBe(lastFocusable);
      fireEvent.keyDown(dialog, { key: 'Tab' });
      const firstRadio = screen.getByLabelText('translation') as HTMLInputElement;
      expect(document.activeElement).toBe(firstRadio);
    });

    it('traps Shift+Tab from the first focusable element to the last', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
      const dialog = screen.getByRole('dialog');
      const firstRadio = screen.getByLabelText('translation') as HTMLInputElement;
      firstRadio.focus();
      expect(document.activeElement).toBe(firstRadio);
      fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
      const lastFocusable = screen.getByRole('button', { name: 'Download JSON' });
      expect(document.activeElement).toBe(lastFocusable);
    });

    it('does not respond to Escape keydown on window (handler is scoped to dialog)', () => {
      render(<FeedbackButton {...baseProps} onDownload={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'Report issue' }));
      expect(screen.getByRole('dialog')).toBeDefined();
      // Firing Escape on window should NOT close the dialog — only keydown on
      // the dialog element does. This ensures no other Escape consumers conflict.
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog')).not.toBeNull();
    });
  });
});

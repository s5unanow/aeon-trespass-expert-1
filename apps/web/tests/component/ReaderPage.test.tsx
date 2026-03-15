import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ReaderPage } from '../../src/routes/ReaderPage';
import sampleRenderPage from '../../public/documents/walking_skeleton/data/render_page.p0001.json';

describe('ReaderPage', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleRenderPage),
    } as Response);
  });

  it('renders the walking skeleton page with heading and icon', async () => {
    render(
      <MemoryRouter initialEntries={['/documents/walking_skeleton/p0001']}>
        <Routes>
          <Route path="/documents/:documentId/:pageId" element={<ReaderPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Проверка атаки')).toBeDefined();
    });

    // Check paragraph text
    expect(screen.getByText('Получите 1')).toBeDefined();

    // Check icon is rendered
    const icon = screen.getByRole('img', { name: 'Прогресс' });
    expect(icon).toBeDefined();

    // Check source page badge
    expect(screen.getByText('p.1')).toBeDefined();
  });
});

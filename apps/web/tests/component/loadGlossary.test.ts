import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearGlossaryCache, loadGlossary } from '../../src/lib/api/loadGlossary';

const sampleGlossary = {
  schema_version: 'glossary_payload.v1',
  document_id: 'test_doc',
  entries: [{ concept_id: 'concept.a', preferred_term: 'A' }],
};

describe('loadGlossary cache', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    clearGlossaryCache();
  });

  it('fetches once and shares the resolved object across repeat calls', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    const first = await loadGlossary('test_doc', 'ru');
    const second = await loadGlossary('test_doc', 'ru');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
  });

  it('fetches separately for different document/edition keys', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    await loadGlossary('test_doc', 'ru');
    await loadGlossary('test_doc', 'en');
    await loadGlossary('other_doc', 'ru');

    expect(fetchSpy).toHaveBeenCalledTimes(3);
  });

  it('does not cache a rejected load — a retry refetches', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    await expect(loadGlossary('test_doc', 'ru')).rejects.toThrow(/Failed to load glossary/);

    // Second call must hit the network again, not replay the cached rejection.
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);
    const retried = await loadGlossary('test_doc', 'ru');

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(retried.document_id).toBe('test_doc');
  });
});

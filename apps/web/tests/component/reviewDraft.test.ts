import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearDraft,
  draftStorageKey,
  emptyDraft,
  loadDraft,
  nextEntryId,
  saveDraft,
  type DraftEntry,
} from '../../src/lib/review/draft';

function entry(): DraftEntry {
  return {
    id: 'text-1',
    scope: 'text',
    blockRef: 'p0001.b002',
    blockIndex: 1,
    reason: 'fix casing',
    summary: 'Text: "…" → "…"',
    operation: { op: 'replace', path: '/blocks/1/children/0/text', value: 'x', scope: 'text' },
  };
}

describe('review draft persistence', () => {
  beforeEach(() => localStorage.clear());

  // Acceptance #7: drafted operations reappear after reload.
  it('round-trips a draft through localStorage', () => {
    const key = draftStorageKey('review_sample', 'en', 'p0001');
    saveDraft(key, { author: 'me', entries: [entry()] });

    const loaded = loadDraft(key);
    expect(loaded.author).toBe('me');
    expect(loaded.entries).toHaveLength(1);
    expect(loaded.entries[0].blockRef).toBe('p0001.b002');
    expect(loaded.entries[0].operation.path).toBe('/blocks/1/children/0/text');
  });

  it('returns an empty draft on a storage miss', () => {
    expect(loadDraft('atr-review-draft:nope')).toEqual(emptyDraft());
  });

  it('returns an empty draft on malformed JSON', () => {
    localStorage.setItem('atr-review-draft:bad', '{not json');
    expect(loadDraft('atr-review-draft:bad')).toEqual(emptyDraft());
  });

  it('clearDraft removes the persisted entry', () => {
    const key = draftStorageKey('d', 'en', 'p0001');
    saveDraft(key, { author: 'a', entries: [entry()] });
    clearDraft(key);
    expect(loadDraft(key)).toEqual(emptyDraft());
  });

  it('scopes the key by document / edition / page', () => {
    expect(draftStorageKey('d', 'en', 'p1')).not.toBe(draftStorageKey('d', 'en', 'p2'));
    expect(draftStorageKey('d', 'en', 'p1')).not.toBe(draftStorageKey('d', 'ru', 'p1'));
  });

  it('nextEntryId is unique per call', () => {
    expect(nextEntryId('text')).not.toBe(nextEntryId('text'));
  });
});

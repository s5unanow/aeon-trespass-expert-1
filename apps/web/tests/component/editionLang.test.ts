import { describe, expect, it } from 'vitest';
import { DEFAULT_READER_LANG, langForEdition } from '../../src/lib/editionLang';

describe('langForEdition', () => {
  it('maps "ru" edition to Russian lang code', () => {
    expect(langForEdition('ru')).toBe('ru');
  });

  it('maps "en" edition to English lang code', () => {
    expect(langForEdition('en')).toBe('en');
  });

  it('falls back to reader default for undefined edition', () => {
    expect(langForEdition(undefined)).toBe(DEFAULT_READER_LANG);
  });

  it('falls back to reader default for unknown edition (not an unrelated language)', () => {
    expect(langForEdition('fr')).toBe(DEFAULT_READER_LANG);
    expect(langForEdition('')).toBe(DEFAULT_READER_LANG);
  });
});

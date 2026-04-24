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

  // S5U-702 (Codex review): the pipeline export contract emits a synthetic
  // "default" edition for documents with a root-level manifest but no
  // per-edition subdirectory. See scripts/export_to_web.py _build_document_index
  // and apps/pipeline/tests/unit/test_export_to_web.py
  // :: test_root_level_manifest_indexed_as_default. Pin the mapping so a
  // careless edit to the helper does not silently break the contract.
  it('maps pipeline synthetic "default" edition to the reader default lang', () => {
    expect(langForEdition('default')).toBe(DEFAULT_READER_LANG);
  });
});

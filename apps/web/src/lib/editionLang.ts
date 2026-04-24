/**
 * Map a route `:edition` parameter to the HTML `lang` attribute value.
 *
 * The reader serves documents in multiple editions (currently `ru` and `en`).
 * The root `<html lang>` must reflect the active edition so accessibility
 * tooling, browser language semantics, and downstream consumers see correct
 * metadata. See S5U-702.
 *
 * Unknown or missing editions fall back to the reader's default shell
 * language (English) — the document index page UI is English, so pre-route
 * state is accurately labelled. This is a reader-defined safe default, not a
 * single-language override of an identifiable non-English edition (the
 * latter is explicitly refused by the issue).
 */

const EDITION_LANG: Record<string, string> = {
  ru: 'ru',
  en: 'en',
};

/** Reader shell default when no edition is active (e.g. on `/`). */
export const DEFAULT_READER_LANG = 'en';

export function langForEdition(edition: string | undefined | null): string {
  if (!edition) return DEFAULT_READER_LANG;
  return EDITION_LANG[edition] ?? DEFAULT_READER_LANG;
}

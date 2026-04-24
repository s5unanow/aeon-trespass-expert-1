/**
 * Map a route `:edition` parameter to the HTML `lang` attribute value.
 *
 * The reader serves documents in multiple editions (currently `ru` and `en`).
 * The root `<html lang>` must reflect the active edition so accessibility
 * tooling, browser language semantics, and downstream consumers see correct
 * metadata. See S5U-702.
 *
 * The map is intentionally explicit and covers every edition string the
 * export pipeline can emit today:
 *
 *   - `ru` / `en` — the two published document editions.
 *   - `default` — a synthetic URL-edition segment that `scripts/export_to_web.py`
 *     emits for documents that have a root-level manifest but no per-edition
 *     subdirectory (see `_build_document_index` in that script and the
 *     `test_root_level_manifest_indexed_as_default` regression test). Its
 *     meaning is explicitly "the content's language cannot be determined from
 *     the URL alone." Per S5U-702's "Must refuse" clause, such cases must fall
 *     back to a reader-defined safe default, not an unrelated language. The
 *     reader shell is English (the index page UI, page chrome, glossary
 *     labels are all English), so mapping `default` → `en` labels the shell
 *     accurately without claiming a specific content language.
 *
 * Any edition string the pipeline introduces in the future that is not in
 * this map also falls through to `DEFAULT_READER_LANG`. If a new edition
 * with a known content language is added (e.g. `fr`), update this map in
 * the same PR. The `Edition` schema type is `string` (open-ended) by
 * contract (`packages/schemas/ts/src/generated/build_manifest_v1.ts`), so
 * the helper is the single source of truth on the web side for the URL
 * edition → lang attribute mapping.
 */

const EDITION_LANG: Record<string, string> = {
  ru: 'ru',
  en: 'en',
  // Language undeterminable from the URL — reader-defined safe default.
  default: 'en',
};

/** Reader shell default when no edition is active (e.g. on `/`). */
export const DEFAULT_READER_LANG = 'en';

export function langForEdition(edition: string | undefined | null): string {
  if (!edition) return DEFAULT_READER_LANG;
  return EDITION_LANG[edition] ?? DEFAULT_READER_LANG;
}
